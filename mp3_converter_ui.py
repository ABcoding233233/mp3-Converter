import queue
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from vid2audconverter import (
    build_item_command,
    build_yt_dlp_command,
    check_dependencies,
    fetch_playlist_entries,
    looks_like_playlist,
    parse_progress_line,
    utf8_subprocess_env,
)


# How many items download/convert at once. 2-3 overlaps a download with the
# previous item's conversion without hammering the connection.
MAX_WORKERS = 3

# Map the friendly dropdown labels to the core quality values.
SOURCE_LABELS = {"Best audio": "best", "Compact": "compact"}
BITRATE_LABELS = {
    "320 kbps": 320,
    "256 kbps": 256,
    "192 kbps": 192,
    "128 kbps": 128,
}


@dataclass
class DownloadJob:
    item_id: str
    url: str
    mode: str
    source: str
    bitrate: int
    status: str = "Queued"
    # playlist_index -> (row iid, item url)
    children: dict = field(default_factory=dict)
    playlist_title: str = ""
    total: int = 0
    remaining: int = 0
    failures: int = 0


@dataclass
class WorkItem:
    job_id: str
    row_id: str
    url: str
    quality: dict
    kind: str = "single"  # "single" | "item" | "playlist_atomic"
    index: int = None
    playlist_title: str = ""
    subfolder: bool = False


class ConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube to MP3")
        self.root.geometry("920x640")
        self.root.minsize(760, 520)

        self.jobs = {}
        self.job_counter = 0
        self.events = queue.Queue()
        self.stop_requested = threading.Event()
        self.active_processes = set()
        self.process_lock = threading.Lock()
        self.worker_thread = None
        self._dependencies = None

        self.mode_var = tk.StringVar(value="auto")
        self.subfolder_var = tk.BooleanVar(value=False)
        self.source_var = tk.StringVar(value="Best audio")
        self.bitrate_var = tk.StringVar(value="320 kbps")
        self.output_dir_var = tk.StringVar(
            value=str(Path(__file__).resolve().parent)
        )
        self.status_var = tk.StringVar(value="Ready")

        self._configure_style()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._drain_events)

    def _configure_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.root.configure(bg="#f5f7fb")
        style.configure("TFrame", background="#f5f7fb")
        style.configure("Panel.TFrame", background="#ffffff", relief="flat")
        style.configure("TLabel", background="#f5f7fb", foreground="#172033")
        style.configure(
            "Panel.TLabel", background="#ffffff", foreground="#172033"
        )
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Muted.TLabel", foreground="#5f6b7a")
        style.configure("TButton", padding=(12, 7))
        style.configure("Accent.TButton", padding=(14, 8))
        style.configure("TEntry", padding=6)
        style.configure(
            "TRadiobutton", background="#ffffff", foreground="#172033"
        )
        style.configure(
            "TCheckbutton", background="#ffffff", foreground="#172033"
        )
        style.configure("Treeview", rowheight=28)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        main = ttk.Frame(self.root, padding=18)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(2, weight=1)
        main.rowconfigure(3, weight=1)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="YouTube to MP3", style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text="Queue links, choose an output folder, and convert to MP3.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        input_panel = ttk.Frame(main, style="Panel.TFrame", padding=14)
        input_panel.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        input_panel.columnconfigure(1, weight=1)

        ttk.Label(input_panel, text="URLs", style="Panel.TLabel").grid(
            row=0, column=0, sticky="nw", padx=(0, 10), pady=(2, 0)
        )
        self.url_text = tk.Text(
            input_panel,
            height=3,
            wrap="word",
            bd=1,
            relief="solid",
            padx=8,
            pady=8,
            font=("Segoe UI", 10),
        )
        self.url_text.grid(row=0, column=1, sticky="ew")
        self.url_text.focus_set()

        self.add_button = ttk.Button(
            input_panel, text="Add to Queue", command=self._add_urls
        )
        self.add_button.grid(row=0, column=2, sticky="ne", padx=(10, 0))

        mode_frame = ttk.Frame(input_panel, style="Panel.TFrame")
        mode_frame.grid(
            row=1, column=1, columnspan=2, sticky="w", pady=(10, 0)
        )
        ttk.Radiobutton(
            mode_frame, text="Auto", value="auto", variable=self.mode_var
        ).grid(row=0, column=0, padx=(0, 14))
        ttk.Radiobutton(
            mode_frame, text="Single", value="single", variable=self.mode_var
        ).grid(row=0, column=1, padx=(0, 14))
        ttk.Radiobutton(
            mode_frame,
            text="Playlist",
            value="playlist",
            variable=self.mode_var,
        ).grid(row=0, column=2)
        self.subfolder_check = ttk.Checkbutton(
            mode_frame,
            text="Playlist subfolder",
            variable=self.subfolder_var,
        )
        self.subfolder_check.grid(row=0, column=3, padx=(24, 0))

        ttk.Label(input_panel, text="Quality", style="Panel.TLabel").grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=(12, 0)
        )
        quality_frame = ttk.Frame(input_panel, style="Panel.TFrame")
        quality_frame.grid(
            row=2, column=1, columnspan=2, sticky="w", pady=(12, 0)
        )
        ttk.Label(quality_frame, text="Source", style="Panel.TLabel").grid(
            row=0, column=0, padx=(0, 6)
        )
        self.source_combo = ttk.Combobox(
            quality_frame,
            textvariable=self.source_var,
            values=list(SOURCE_LABELS),
            state="readonly",
            width=12,
        )
        self.source_combo.grid(row=0, column=1, padx=(0, 18))
        ttk.Label(quality_frame, text="Bitrate", style="Panel.TLabel").grid(
            row=0, column=2, padx=(0, 6)
        )
        self.bitrate_combo = ttk.Combobox(
            quality_frame,
            textvariable=self.bitrate_var,
            values=list(BITRATE_LABELS),
            state="readonly",
            width=10,
        )
        self.bitrate_combo.grid(row=0, column=3)

        ttk.Label(input_panel, text="Output", style="Panel.TLabel").grid(
            row=3, column=0, sticky="w", padx=(0, 10), pady=(12, 0)
        )
        self.output_entry = ttk.Entry(
            input_panel, textvariable=self.output_dir_var
        )
        self.output_entry.grid(row=3, column=1, sticky="ew", pady=(12, 0))
        self.browse_button = ttk.Button(
            input_panel, text="Browse", command=self._choose_output_dir
        )
        self.browse_button.grid(
            row=3, column=2, sticky="e", padx=(10, 0), pady=(12, 0)
        )

        queue_panel = ttk.Frame(main, style="Panel.TFrame", padding=14)
        queue_panel.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        queue_panel.columnconfigure(0, weight=1)
        queue_panel.rowconfigure(1, weight=1)

        queue_header = ttk.Frame(queue_panel, style="Panel.TFrame")
        queue_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        queue_header.columnconfigure(0, weight=1)
        ttk.Label(queue_header, text="Queue", style="Panel.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            queue_header, textvariable=self.status_var, style="Panel.TLabel"
        ).grid(row=0, column=1, sticky="e")

        queue_body = ttk.Frame(queue_panel, style="Panel.TFrame")
        queue_body.grid(row=1, column=0, sticky="nsew")
        queue_body.columnconfigure(0, weight=1)
        queue_body.rowconfigure(0, weight=1)

        columns = ("mode", "status")
        self.queue_tree = ttk.Treeview(
            queue_body,
            columns=columns,
            show="tree headings",
            selectmode="extended",
        )
        self.queue_tree.heading("#0", text="URL / Title")
        self.queue_tree.heading("mode", text="Mode")
        self.queue_tree.heading("status", text="Status")
        self.queue_tree.column("#0", minwidth=260, width=520, stretch=True)
        self.queue_tree.column(
            "mode", minwidth=80, width=90, stretch=False, anchor="center"
        )
        self.queue_tree.column(
            "status", minwidth=120, width=160, stretch=False, anchor="center"
        )
        self.queue_tree.grid(row=0, column=0, sticky="nsew")

        queue_scroll = ttk.Scrollbar(
            queue_body, orient="vertical", command=self.queue_tree.yview
        )
        queue_scroll.grid(row=0, column=1, sticky="ns")
        self.queue_tree.configure(yscrollcommand=queue_scroll.set)

        queue_actions = ttk.Frame(queue_panel, style="Panel.TFrame")
        queue_actions.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        queue_actions.columnconfigure(0, weight=1)

        self.remove_button = ttk.Button(
            queue_actions,
            text="Remove Selected",
            command=self._remove_selected,
        )
        self.remove_button.grid(row=0, column=0, sticky="w")
        self.clear_button = ttk.Button(
            queue_actions, text="Clear Finished", command=self._clear_finished
        )
        self.clear_button.grid(row=0, column=1, padx=(8, 0))
        self.start_button = ttk.Button(
            queue_actions,
            text="Start Queue",
            style="Accent.TButton",
            command=self._start_queue,
        )
        self.start_button.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self.stop_button = ttk.Button(
            queue_actions,
            text="Stop",
            command=self._stop_queue,
            state="disabled",
        )
        self.stop_button.grid(row=0, column=3, sticky="e", padx=(8, 0))

        log_panel = ttk.Frame(main, style="Panel.TFrame", padding=14)
        log_panel.grid(row=3, column=0, sticky="nsew")
        log_panel.columnconfigure(0, weight=1)
        log_panel.rowconfigure(1, weight=1)

        log_header = ttk.Frame(log_panel, style="Panel.TFrame")
        log_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        log_header.columnconfigure(0, weight=1)
        ttk.Label(log_header, text="Log", style="Panel.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(log_header, text="Clear Log", command=self._clear_log).grid(
            row=0, column=1, sticky="e"
        )

        self.log_text = scrolledtext.ScrolledText(
            log_panel,
            height=8,
            wrap="word",
            state="disabled",
            bd=1,
            relief="solid",
            padx=8,
            pady=8,
            font=("Consolas", 9),
        )
        self.log_text.grid(row=1, column=0, sticky="nsew")

    def _add_urls(self):
        raw = self.url_text.get("1.0", "end").strip()
        urls = [line.strip() for line in raw.splitlines() if line.strip()]
        if not urls:
            messagebox.showinfo(
                "No URL", "Paste one or more YouTube URLs first."
            )
            return

        mode = self.mode_var.get()
        source = SOURCE_LABELS[self.source_var.get()]
        bitrate = BITRATE_LABELS[self.bitrate_var.get()]

        for url in urls:
            self.job_counter += 1
            item_id = f"job_{self.job_counter}"
            job = DownloadJob(
                item_id=item_id,
                url=url,
                mode=mode,
                source=source,
                bitrate=bitrate,
            )
            self.jobs[item_id] = job
            self.queue_tree.insert(
                "",
                "end",
                iid=item_id,
                text=url,
                values=(self._mode_label(mode), job.status),
                open=True,
            )

            # Pre-fetch playlist tracks so their rows show up before the queue
            # starts. Runs off the UI thread; falls back to a single row.
            if self._resolve_playlist_mode(url, mode):
                self.queue_tree.set(item_id, "status", "Fetching…")
                threading.Thread(
                    target=self._prefetch_playlist,
                    args=(item_id, url),
                    daemon=True,
                ).start()

        self.url_text.delete("1.0", "end")
        self._set_status(f"Queued {len(urls)} item(s)")

    def _remove_selected(self):
        for item_id in self.queue_tree.selection():
            self.jobs.pop(item_id, None)
            self.queue_tree.delete(item_id)
        self._set_status("Ready")

    def _clear_finished(self):
        finished = {"Done", "Partial", "Failed", "Canceled"}
        for item_id, job in list(self.jobs.items()):
            if job.status in finished:
                self.jobs.pop(item_id, None)
                self.queue_tree.delete(item_id)
        self._set_status("Ready")

    def _choose_output_dir(self):
        folder = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if folder:
            self.output_dir_var.set(folder)

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _get_dependencies(self):
        """Return cached dependencies, or None if yt-dlp/FFmpeg are missing."""
        if self._dependencies is None:
            try:
                self._dependencies = check_dependencies()
            except Exception:
                return None
        return self._dependencies

    def _prefetch_playlist(self, item_id, url):
        """Fetch a playlist's track list off the UI thread (background)."""
        dependencies = self._get_dependencies()
        if dependencies is not None:
            entries, playlist_title = fetch_playlist_entries(url, dependencies)
        else:
            entries, playlist_title = [], ""
        self._post("prefetch_done", item_id, entries, playlist_title)

    def _add_playlist_children(self, item_id, entries, playlist_title):
        """Populate a playlist job's child rows (runs on the UI thread)."""
        job = self.jobs.get(item_id)
        if not job or not self.queue_tree.exists(item_id):
            return

        if not entries:
            # Could not enumerate the playlist; keep it as a single row and
            # let it run atomically.
            self.queue_tree.set(item_id, "status", job.status)
            return

        job.children.clear()
        job.playlist_title = playlist_title
        job.total = len(entries)
        for index, title, url in entries:
            child_id = f"{item_id}_item_{index}"
            job.children[index] = (child_id, url)
            if self.queue_tree.exists(child_id):
                self.queue_tree.delete(child_id)
            self.queue_tree.insert(
                item_id,
                "end",
                iid=child_id,
                text=f"{index:03d} - {title}",
                values=("", "Queued"),
            )
        self.queue_tree.set(item_id, "status", f"Queued ({job.total} items)")

    def _start_queue(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return

        queued_jobs = [
            job for job in self.jobs.values() if job.status == "Queued"
        ]
        if not queued_jobs:
            messagebox.showinfo(
                "Queue Empty", "Add at least one queued URL first."
            )
            return

        raw_output = self.output_dir_var.get().strip()
        if not raw_output:
            messagebox.showinfo(
                "No Output Folder", "Choose an output folder first."
            )
            return

        output_dir = Path(raw_output).expanduser().resolve()
        if output_dir.exists() and not output_dir.is_dir():
            messagebox.showinfo(
                "Invalid Output Folder",
                "That path points to a file, not a folder.",
            )
            return

        # Reflect the cleaned, absolute path back into the entry so the user
        # sees exactly where files will go (strips stray spaces, resolves
        # relative paths and mixed slashes).
        self.output_dir_var.set(str(output_dir))

        playlist_subfolder = self.subfolder_var.get()
        work_items = self._build_work_items(queued_jobs, playlist_subfolder)

        self.stop_requested.clear()
        self._set_running(True)
        self.worker_thread = threading.Thread(
            target=self._run_pool,
            args=(work_items, output_dir),
            daemon=True,
        )
        self.worker_thread.start()

    def _build_work_items(self, queued_jobs, playlist_subfolder):
        """Flatten queued jobs into individual download work items.

        A playlist with known tracks becomes one work item per track (so they
        can run in parallel); otherwise the job is a single work item.
        """
        work_items = []
        for job in queued_jobs:
            quality = {"source": job.source, "bitrate": job.bitrate}
            playlist_mode = self._resolve_playlist_mode(job.url, job.mode)
            job.failures = 0

            if playlist_mode and job.children:
                job.total = job.remaining = len(job.children)
                title = job.playlist_title if playlist_subfolder else ""
                for index in sorted(job.children):
                    child_id, url = job.children[index]
                    work_items.append(
                        WorkItem(
                            job_id=job.item_id,
                            row_id=child_id,
                            url=url,
                            quality=quality,
                            kind="item",
                            index=index,
                            playlist_title=title,
                        )
                    )
            elif playlist_mode:
                job.total = job.remaining = 1
                work_items.append(
                    WorkItem(
                        job_id=job.item_id,
                        row_id=job.item_id,
                        url=job.url,
                        quality=quality,
                        kind="playlist_atomic",
                        subfolder=playlist_subfolder,
                    )
                )
            else:
                job.total = job.remaining = 1
                work_items.append(
                    WorkItem(
                        job_id=job.item_id,
                        row_id=job.item_id,
                        url=job.url,
                        quality=quality,
                        kind="single",
                    )
                )
        return work_items

    def _stop_queue(self):
        self.stop_requested.set()
        self._terminate_active_processes()
        self._set_status("Stopping...")

    def _terminate_active_processes(self):
        with self.process_lock:
            processes = list(self.active_processes)
        for process in processes:
            if process.poll() is None:
                process.terminate()

    def _on_close(self):
        running = self.worker_thread and self.worker_thread.is_alive()
        if running:
            should_close = messagebox.askyesno(
                "Stop Conversion",
                "A conversion is still running. Stop it and close the app?",
            )
            if not should_close:
                return
            self.stop_requested.set()
            self._terminate_active_processes()

        self.root.destroy()

    def _run_pool(self, work_items, output_dir):
        """Manager thread: run work items through a pool of N workers."""
        dependencies = self._get_dependencies()
        if dependencies is None:
            self._post("log", "Setup error: yt-dlp or FFmpeg is missing.")
            self._post("statusbar", "Setup error")
            self._post("running", False)
            return

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self._post("log", f"Setup error: {exc}")
            self._post("statusbar", "Setup error")
            self._post("running", False)
            return

        work_queue = queue.Queue()
        for item in work_items:
            work_queue.put(item)

        self._post("statusbar", "Running")
        worker_count = min(MAX_WORKERS, len(work_items)) or 1
        threads = []
        for _ in range(worker_count):
            thread = threading.Thread(
                target=self._pool_worker,
                args=(work_queue, output_dir, dependencies),
                daemon=True,
            )
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        final_status = "Stopped" if self.stop_requested.is_set() else "Ready"
        self._post("statusbar", final_status)
        self._post("running", False)

    def _pool_worker(self, work_queue, output_dir, dependencies):
        while not self.stop_requested.is_set():
            try:
                item = work_queue.get_nowait()
            except queue.Empty:
                return
            self._process_work_item(item, output_dir, dependencies)

    def _process_work_item(self, item, output_dir, dependencies):
        self._post("row_status", item.row_id, "Downloading…")
        self._post("log", f"Starting: {item.url}")

        try:
            command = self._build_item_command(item, output_dir, dependencies)
            return_code, saw_error = self._run_process(command, item.row_id)
        except Exception as exc:
            self._post("log", f"Failed: {item.url}: {exc}")
            self._post("item_done", item, -1, False)
            return

        self._post("item_done", item, return_code, saw_error)

    def _build_item_command(self, item, output_dir, dependencies):
        if item.kind == "playlist_atomic":
            return build_yt_dlp_command(
                source_url=item.url,
                output_dir=output_dir,
                playlist_mode=True,
                dependencies=dependencies,
                playlist_subfolder=item.subfolder,
                quality=item.quality,
            )
        return build_item_command(
            item.url,
            output_dir,
            dependencies,
            quality=item.quality,
            index=item.index,
            playlist_title=item.playlist_title or None,
        )

    def _run_process(self, command, row_id):
        startupinfo = None
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            startupinfo=startupinfo,
            env=utf8_subprocess_env(),
        )
        with self.process_lock:
            self.active_processes.add(process)

        saw_error = False
        try:
            if process.stdout:
                for line in process.stdout:
                    clean_line = line.rstrip()
                    if clean_line:
                        progress = parse_progress_line(clean_line)
                        if progress is not None:
                            self._post("progress", row_id, progress)
                        else:
                            if clean_line.startswith("ERROR"):
                                saw_error = True
                            self._post("log", clean_line)
                    if self.stop_requested.is_set() and process.poll() is None:
                        process.terminate()

            return process.wait(), saw_error
        finally:
            with self.process_lock:
                self.active_processes.discard(process)

    def _resolve_playlist_mode(self, url, mode):
        if mode == "playlist":
            return True
        if mode == "single":
            return False
        return looks_like_playlist(url)

    def _mode_label(self, mode):
        return {
            "auto": "Auto",
            "single": "Single",
            "playlist": "Playlist",
        }.get(mode, mode.title())

    def _post(self, event_type, *payload):
        self.events.put((event_type, payload))

    def _drain_events(self):
        while True:
            try:
                event_type, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event_type == "log":
                self._append_log(payload[0])
            elif event_type == "row_status":
                self._set_row_status(payload[0], payload[1])
            elif event_type == "statusbar":
                self._set_status(payload[0])
            elif event_type == "running":
                self._set_running(payload[0])
            elif event_type == "progress":
                self._update_progress(payload[0], payload[1])
            elif event_type == "item_done":
                self._on_item_done(payload[0], payload[1], payload[2])
            elif event_type == "prefetch_done":
                self._add_playlist_children(
                    payload[0], payload[1], payload[2]
                )

        self.root.after(100, self._drain_events)

    def _append_log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_row_status(self, row_id, status):
        """Set a row's Status text; if the row is a job, track job.status too."""
        job = self.jobs.get(row_id)
        if job:
            job.status = status
        if self.queue_tree.exists(row_id):
            self.queue_tree.set(row_id, "status", status)

    def _update_progress(self, row_id, progress):
        """Show a live progress label on the row that produced it."""
        if self.queue_tree.exists(row_id):
            self.queue_tree.set(
                row_id, "status", self._progress_label(progress)
            )

    def _progress_label(self, progress):
        """Turn a progress dict into a short status string for a row."""
        finished = progress["status"] == "finished"
        if progress["phase"] == "convert":
            return "Done" if finished else "Converting…"
        if finished:
            return "Converting…"
        percent = progress["percent"]
        if percent is not None:
            return f"Downloading {percent:.0f}%"
        return "Downloading…"

    def _on_item_done(self, item, return_code, saw_error):
        """Finalize one work item and roll its result into the parent job."""
        canceled = self.stop_requested.is_set() and return_code != 0
        if canceled:
            status = "Canceled"
        elif return_code != 0:
            status = "Failed"
        elif saw_error:
            status = "Partial"
        else:
            status = "Done"

        if self.queue_tree.exists(item.row_id):
            self.queue_tree.set(item.row_id, "status", status)

        job = self.jobs.get(item.job_id)
        if not job:
            return

        if item.row_id == item.job_id:
            # Single video or atomic playlist: the row is the job itself.
            job.status = status
            return

        # A playlist track finished: update counts and the parent summary.
        job.remaining = max(0, job.remaining - 1)
        if status in ("Failed", "Canceled"):
            job.failures += 1

        if not self.queue_tree.exists(item.job_id):
            return
        if job.remaining == 0:
            job.status = self._playlist_final_status(job)
            self.queue_tree.set(item.job_id, "status", job.status)
        else:
            completed = job.total - job.remaining
            pct = int(completed / job.total * 100) if job.total else 0
            self.queue_tree.set(
                item.job_id, "status", f"{pct}% ({completed}/{job.total})"
            )

    def _playlist_final_status(self, job):
        if job.failures == 0:
            return "Done"
        if job.failures >= job.total:
            return "Failed"
        return "Partial"

    def _set_status(self, status):
        self.status_var.set(status)

    def _set_running(self, running):
        if running:
            self._set_status("Running")
        normal = "normal"
        disabled = "disabled"
        editable_state = disabled if running else normal

        self.add_button.configure(state=editable_state)
        self.remove_button.configure(state=editable_state)
        self.clear_button.configure(state=editable_state)
        self.browse_button.configure(state=editable_state)
        self.output_entry.configure(state=editable_state)
        self.subfolder_check.configure(state=editable_state)
        combo_state = disabled if running else "readonly"
        self.source_combo.configure(state=combo_state)
        self.bitrate_combo.configure(state=combo_state)
        self.start_button.configure(state=disabled if running else normal)
        self.stop_button.configure(state=normal if running else disabled)
        self.url_text.configure(state=disabled if running else normal)


def main():
    root = tk.Tk()
    ConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
