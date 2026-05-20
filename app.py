import os
import sys
import json
import threading
import wave
from datetime import datetime
import glob
import urllib.request
import zipfile
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# --- Профильтрованный список слов ---
DEFAULT_WORDS = [
    "блять", "блядь", "бля", "сука", "хуй", "хуя", "хуе", "пизд", "пиздец",
    "ебат", "ебан", "ебать", "нахуй", "похуй", "заеб", "уеб", "отъеб",
    "долбоёб", "долбоеб", "мудак", "мудила", "залуп", "шлюх", "пидор",
    "еблан", "дебил", "чмо", "лох", "гандон", "гондон", "говно", "жопа"
]

SETTINGS_FILE = "vm_settings.json"
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
MUSIC_DIR = "music"


def get_base():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_model_dir():
    return os.path.join(get_base(), "model")


def load_settings():
    p = os.path.join(get_base(), SETTINGS_FILE)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_settings(s):
    p = os.path.join(get_base(), SETTINGS_FILE)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)


def get_rec_dir(settings):
    d = settings.get("rec_dir", "")
    if not d:
        d = os.path.join(get_base(), "recordings")
    os.makedirs(d, exist_ok=True)
    return d


def has_profane(text, words):
    t = text.lower()
    for w in words:
        if w in t:
            return True
    return False


class SetupWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("VoiceMonitor — Настройка")
        self.geometry("480x340")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None

        bg = "#1a1a2e"
        self.configure(bg=bg)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background=bg, foreground="#ffffff", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=bg, foreground="#a29bfe", font=("Segoe UI", 13, "bold"))
        style.configure("TButton", font=("Segoe UI", 10), padding=(16, 5))
        style.configure("Accent.TButton", background="#6c5ce7", foreground="#ffffff", font=("Segoe UI", 10, "bold"))

        ttk.Label(self, text="Первый запуск — выберите папку", style="Title.TLabel").pack(pady=(20, 12))

        self.dir_var = tk.StringVar()
        mode = tk.StringVar(value="default")

        def on_mode(*_):
            if mode.get() == "custom":
                f.pack(fill="x", padx=40, pady=4)
            else:
                f.pack_forget()

        mode.trace_add("write", on_mode)

        items = [
            ("default", "Рядом с программой (рекомендуется)"),
            ("docs", "Мои документы"),
            ("desktop", "Рабочий стол"),
            ("custom", "Своя папка..."),
        ]
        for val, txt in items:
            ttk.Radiobutton(self, text=txt, variable=mode, value=val).pack(anchor="w", padx=24, pady=2)

        f = ttk.Frame(self)
        ttk.Entry(f, textvariable=self.dir_var, width=35).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(f, text="...", command=self.browse).pack(side="right")

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=24, pady=12)

        ttk.Button(self, text="Начать", style="Accent.TButton",
                   command=lambda: self.apply(mode.get())).pack(pady=(4, 8))

    def browse(self):
        d = filedialog.askdirectory()
        if d:
            self.dir_var.set(d)

    def apply(self, mode):
        base = get_base()
        if mode == "default":
            path = os.path.join(base, "recordings")
        elif mode == "docs":
            path = os.path.join(os.path.expanduser("~/Documents"), "VoiceMonitor")
        elif mode == "desktop":
            path = os.path.join(os.path.expanduser("~/Desktop"), "VoiceMonitor")
        else:
            path = self.dir_var.get().strip()
            if not path:
                messagebox.showwarning("Внимание", "Выберите папку.")
                return

        os.makedirs(path, exist_ok=True)
        self.result = {
            "rec_dir": path,
            "words": list(DEFAULT_WORDS),
            "post_sec": 3,
        }
        save_settings(self.result)
        self.destroy()


class DownloadDialog(tk.Toplevel):
    def __init__(self, parent, model_dir):
        super().__init__(parent)
        self.title("Скачивание модели")
        self.geometry("420x220")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.done = False

        bg = "#1a1a2e"
        self.configure(bg=bg)

        ttk.Label(self, text="Модель не найдена", foreground="#a29bfe",
                  background=bg, font=("Segoe UI", 11, "bold")).pack(pady=(18, 6))
        ttk.Label(self, text="Нужно скачать модель (~50 MB) один раз",
                  foreground="#a0a0b0", background=bg).pack()

        self.progress = ttk.Progressbar(self, mode="determinate", length=320)
        self.progress.pack(pady=14)

        self.status = ttk.Label(self, text="", foreground="#a0a0b0", background=bg)
        self.status.pack()

        self.btn = tk.Button(self, text="Скачать", bg="#6c5ce7", fg="white",
                             relief="flat", font=("Segoe UI", 10, "bold"), cursor="hand2",
                             padx=16, pady=6, command=self.start_download)
        self.btn.pack(pady=(8, 4))

        self.model_dir = model_dir

    def start_download(self):
        self.btn.config(state="disabled", text="Скачивание...")
        t = threading.Thread(target=self._download, daemon=True)
        t.start()

    def _download(self):
        tmp = os.path.join(get_base(), "_tmp_model.zip")
        try:
            def hook(n, bs, ts):
                if ts > 0:
                    pct = min(100, n * bs * 100 // ts)
                    self.after(0, lambda: (self.progress.configure(value=pct),
                                           self.status.config(text=f"Скачивание: {pct}%")))

            urllib.request.urlretrieve(MODEL_URL, tmp, reporthook=hook)
            self.after(0, lambda: self.status.config(text="Распаковка..."))

            os.makedirs(self.model_dir, exist_ok=True)
            with zipfile.ZipFile(tmp) as z:
                z.extractall(self.model_dir)
            os.remove(tmp)

            inner = os.path.join(self.model_dir, "vosk-model-small-ru-0.22")
            if os.path.isdir(inner):
                for name in os.listdir(inner):
                    src = os.path.join(inner, name)
                    dst = os.path.join(self.model_dir, name)
                    if os.path.exists(dst):
                        if os.path.isdir(dst):
                            shutil.rmtree(dst)
                        else:
                            os.remove(dst)
                    shutil.move(src, dst)
                os.rmdir(inner)

            self.after(0, lambda: (self.status.config(text="Готово!", foreground="#28a745"),
                                   self.btn.config(text="OK", state="normal", command=self._close)))
            self.done = True
        except Exception as e:
            msg = str(e)[:100]
            self.after(0, lambda: (self.status.config(text=f"Ошибка: {msg}", foreground="#dc3545"),
                                   self.btn.config(text="Повторить", state="normal", command=self.start_download)))

    def _close(self):
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VoiceMonitor — Контроль речи")
        self.geometry("900x580")
        self.minsize(720, 420)
        self.configure(bg="#1a1a2e")

        style = ttk.Style()
        style.theme_use("clam")

        bg = "#1a1a2e"
        accent = "#6c5ce7"
        light = "#a29bfe"
        green = "#28a745"
        red = "#dc3545"

        style.configure("Treeview", background="#22223a", foreground="#ffffff",
                        fieldbackground="#22223a", borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#2d2d44", foreground=light,
                        font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("Treeview.Heading", background=[("active", "#3d3d55")])
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground="#ffffff")

        # Загрузка настроек
        self.settings = load_settings()
        if not self.settings:
            self.withdraw()
            dlg = SetupWindow(self)
            self.wait_window(dlg)
            if dlg.result:
                self.settings = dlg.result
            else:
                self.quit()
                return

        self.rec_dir = get_rec_dir(self.settings)
        self.words = self.settings.get("words", DEFAULT_WORDS)
        self.post_sec = self.settings.get("post_sec", 3)
        self.music_volume = self.settings.get("music_volume", 0.7)
        self.music_dir = os.path.join(get_base(), MUSIC_DIR)
        os.makedirs(self.music_dir, exist_ok=True)
        self.music_tracks = self._scan_music()
        self.current_track = None
        self.music_playing = False
        self.music_thread = None

        # Кнопки
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=6)

        self.btn_start = tk.Button(toolbar, text="▶  Старт", bg=green, fg="white",
                                   relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2",
                                   padx=12, pady=5, command=self.start)
        self.btn_start.pack(side="left", padx=(4, 4))

        self.btn_stop = tk.Button(toolbar, text="■  Стоп", bg=red, fg="white",
                                  relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2",
                                  padx=12, pady=5, state="disabled", command=self.stop)
        self.btn_stop.pack(side="left", padx=4)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        # Музыка
        music_frame = ttk.Frame(toolbar)
        music_frame.pack(side="left", padx=4)

        ttk.Label(music_frame, text="Музыка:", foreground=light).pack(side="left", padx=(0, 4))

        self.music_var = tk.StringVar(value="Нет треков")
        self.music_combo = ttk.Combobox(music_frame, textvariable=self.music_var, width=20, state="readonly")
        if self.music_tracks:
            self.music_combo["values"] = self.music_tracks
            self.music_combo.current(0)
        self.music_combo.pack(side="left", padx=2)

        self.btn_music_play = tk.Button(music_frame, text="▶", bg=green, fg="white",
                                        relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2",
                                        width=3, command=self.music_toggle)
        self.btn_music_play.pack(side="left", padx=2)

        tk.Button(music_frame, text="📂", bg=accent, fg="white",
                  relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2",
                  width=3, command=self.open_music_folder).pack(side="left", padx=2)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        tk.Button(toolbar, text="⚙  Настройки", bg=accent, fg="white",
                  relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2",
                  padx=12, pady=5, command=self.show_settings).pack(side="left", padx=4)

        tk.Button(toolbar, text="📂  Папка", bg=accent, fg="white",
                  relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2",
                  padx=12, pady=5, command=self.open_folder).pack(side="left", padx=4)

        tk.Button(toolbar, text="🗑  Очистить", bg=accent, fg="white",
                  relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2",
                  padx=12, pady=5, command=self.clear_log).pack(side="left", padx=4)

        # Таблица
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=8, pady=4)

        self.tree = ttk.Treeview(frame, columns=("date", "time", "text", "file"), show="headings")
        self.tree.heading("date", text="Дата")
        self.tree.heading("time", text="Время")
        self.tree.heading("text", text="Распознанный текст")
        self.tree.heading("file", text="Файл")
        self.tree.column("date", width=85, anchor="center")
        self.tree.column("time", width=75, anchor="center")
        self.tree.column("text", width=340)
        self.tree.column("file", width=200)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._open_file)

        # Статус
        sf = ttk.Frame(self)
        sf.pack(fill="x")
        self.status_lbl = tk.Label(sf, text="Загрузка модели...", bg=bg, fg=light, font=("Segoe UI", 9))
        self.status_lbl.pack(side="left", padx=12, pady=4)

        # Модель
        self.after(100, self._ensure_model)

    def _ensure_model(self):
        md = get_model_dir()
        if os.path.isdir(md) and len(os.listdir(md)) > 5:
            self._load_model(md)
        else:
            dlg = DownloadDialog(self, md)
            self.wait_window(dlg)
            if dlg.done:
                self._load_model(md)
            else:
                self.status_lbl.config(text="Модель не установлена")

    def _load_model(self, md):
        try:
            from vosk import Model, KaldiRecognizer
            self.vosk_model = Model(md)
            self.recognizer = KaldiRecognizer(self.vosk_model, 16000)
            self.recognizer.SetWords(True)
            self.status_lbl.config(text="Готово — нажмите «Старт»", fg="#28a745")
            self._load_log()
        except Exception as e:
            self.status_lbl.config(text=f"Ошибка модели: {e}", fg="#dc3545")

    def start(self):
        if not hasattr(self, "vosk_model"):
            messagebox.showwarning("Ошибка", "Модель не загружена.")
            return
        self.running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status_lbl.config(text="● Слушаю...", fg="#28a745")

        self.audio = []
        self.posting = False
        self.post_n = 0
        self.det_time = None
        self.det_text = ""

        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        self.running = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.status_lbl.config(text="Готово", fg="#a29bfe")

    def _scan_music(self):
        tracks = []
        for ext in (".mp3", ".wav", ".ogg", ".flac", ".m4a"):
            tracks.extend(glob.glob(os.path.join(self.music_dir, f"*{ext}")))
        return [os.path.basename(t) for t in sorted(tracks)]

    def music_toggle(self):
        if not self.music_tracks:
            messagebox.showinfo("Музыка", f"Добавьте mp3/wav файлы в папку:\n{self.music_dir}")
            return
        if self.music_playing:
            self.music_stop()
        else:
            self.music_play()

    def music_play(self):
        selected = self.music_var.get()
        if selected not in self.music_tracks:
            return
        self.current_track = selected
        self.music_playing = True
        self.btn_music_play.config(text="⏸", bg="#ffc107")
        t = threading.Thread(target=self._music_loop, daemon=True)
        t.start()

    def music_stop(self):
        self.music_playing = False
        self.btn_music_play.config(text="▶", bg="#28a745")

    def _music_loop(self):
        try:
            import pygame
        except ImportError:
            self.after(0, lambda: messagebox.showerror("Ошибка", "Установите pygame: pip install pygame"))
            self.after(0, self.music_stop)
            return

        pygame.mixer.init()
        track_path = os.path.join(self.music_dir, self.current_track)

        while self.music_playing:
            try:
                pygame.mixer.music.load(track_path)
                pygame.mixer.music.set_volume(self.music_volume)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy() and self.music_playing:
                    pygame.time.wait(200)
            except Exception as e:
                self.after(0, lambda: self.status_lbl.config(text=f"Ошибка музыки: {e}", fg="#dc3545"))
                break

    def open_music_folder(self):
        os.makedirs(self.music_dir, exist_ok=True)
        os.startfile(self.music_dir)

    def _loop(self):
        try:
            from pyaudio import PyAudio, paInt16
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Ошибка", f"PyAudio: {e}"))
            self.after(0, self.stop)
            return

        pa = PyAudio()
        try:
            stream = pa.open(format=paInt16, channels=1, rate=16000,
                             input=True, frames_per_buffer=3200)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Ошибка", f"Микрофон: {e}"))
            self.after(0, self.stop)
            return

        post_total = self.post_sec * 5

        try:
            while self.running:
                try:
                    data = stream.read(3200, exception_on_overflow=False)
                except Exception:
                    continue

                self.audio.append(data)

                if self.recognizer.AcceptWaveform(data):
                    import json as _j
                    res = _j.loads(self.recognizer.Result())
                    text = res.get("text", "")
                    if text and has_profane(text, self.words):
                        self.det_time = datetime.now()
                        self.det_text = text
                        self.posting = True
                        self.post_n = 0
                        continue

                if self.posting:
                    self.post_n += 1
                    if self.post_n >= post_total:
                        self.after(0, self._save)
                        self.posting = False
                        self.post_n = 0
                        self.audio = []
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def _save(self):
        try:
            ts = self.det_time.strftime("%Y-%m-%d_%H-%M-%S")
            fn = f"detect_{ts}.wav"
            fp = os.path.join(self.rec_dir, fn)
            raw = b"".join(self.audio)
            with wave.open(fp, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(raw)

            month = self.det_time.strftime("%Y-%m")
            lp = os.path.join(self.rec_dir, f"detections_{month}.json")
            entries = []
            if os.path.exists(lp):
                with open(lp, "r", encoding="utf-8") as f:
                    entries = json.load(f)

            entry = {
                "date": self.det_time.strftime("%d.%m.%Y"),
                "time": self.det_time.strftime("%H:%M:%S"),
                "text": self.det_text,
                "file": fn,
            }
            entries.append(entry)
            with open(lp, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)

            self.tree.insert("", 0, values=(entry["date"], entry["time"], entry["text"], entry["file"]))
            self.status_lbl.config(text=f"Детекция: {entry['time']}")

            self.audio = []
        except Exception as e:
            print("Save error:", e)

    def _load_log(self):
        self.tree.delete(*self.tree.get_children())
        logs = sorted(glob.glob(os.path.join(self.rec_dir, "detections_*.json")), reverse=True)[:10]
        for lp in logs:
            try:
                with open(lp, "r", encoding="utf-8") as f:
                    entries = json.load(f)
                for e in reversed(entries):
                    self.tree.insert("", 0, values=(e["date"], e["time"], e["text"], e["file"]))
            except Exception:
                pass

    def show_settings(self):
        w = tk.Toplevel(self)
        w.title("Настройки")
        w.geometry("460x520")
        w.resizable(False, False)
        w.transient(self)
        w.grab_set()

        bg = "#1a1a2e"
        w.configure(bg=bg)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background=bg, foreground="#ffffff")
        style.configure("TButton", padding=(14, 5))
        style.configure("Accent.TButton", background="#6c5ce7", foreground="#ffffff")

        ttk.Label(w, text="Папка записей:", foreground="#a29bfe").pack(anchor="w", padx=16, pady=(14, 4))

        dv = tk.StringVar(value=self.rec_dir)
        fr = ttk.Frame(w)
        fr.pack(fill="x", padx=16)
        ttk.Entry(fr, textvariable=dv, width=35).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(fr, text="...", command=lambda: dv.set(filedialog.askdirectory())).pack(side="right")

        ttk.Label(w, text="Пост-запись (сек):", foreground="#a29bfe").pack(anchor="w", padx=16, pady=(12, 4))
        pv = tk.IntVar(value=self.post_sec)
        ttk.Spinbox(w, from_=1, to=30, textvariable=pv, width=5).pack(anchor="w", padx=16)

        ttk.Label(w, text="Громкость музыки:", foreground="#a29bfe").pack(anchor="w", padx=16, pady=(12, 4))
        vv = tk.DoubleVar(value=self.music_volume)
        scale = tk.Scale(w, from_=0, to=1, resolution=0.1, orient="horizontal",
                         variable=vv, bg=bg, fg="#ffffff", highlightthickness=0)
        scale.pack(fill="x", padx=16)

        ttk.Label(w, text="Слова для поиска:", foreground="#a29bfe").pack(anchor="w", padx=16, pady=(12, 4))
        tw = tk.Text(w, height=10, bg="#22223a", fg="#ffffff", insertbackground="#ffffff",
                     font=("Consolas", 9), relief="flat")
        tw.pack(fill="both", padx=16, pady=(0, 12), expand=True)
        tw.insert("1.0", "\n".join(self.words))

        def save():
            d = dv.get().strip()
            if not d:
                messagebox.showwarning("Внимание", "Укажите папку.")
                return
            self.settings["rec_dir"] = d
            self.settings["post_sec"] = pv.get()
            self.settings["music_volume"] = vv.get()
            self.music_volume = vv.get()
            self.settings["words"] = [x.strip().lower() for x in tw.get("1.0", "end-1c").split("\n") if x.strip()]
            self.rec_dir = get_rec_dir(self.settings)
            self.words = self.settings["words"]
            self.post_sec = self.settings["post_sec"]
            save_settings(self.settings)
            w.destroy()

        fr2 = ttk.Frame(w)
        fr2.pack(fill="x", padx=16)
        ttk.Button(fr2, text="Сохранить", style="Accent.TButton", command=save).pack(side="right", padx=(6, 0))
        ttk.Button(fr2, text="Закрыть", command=w.destroy).pack(side="right")

    def open_folder(self):
        if os.path.exists(self.rec_dir):
            os.startfile(self.rec_dir)

    def clear_log(self):
        if messagebox.askyesno("Очистить", "Удалить все записи и логи?"):
            for f in glob.glob(os.path.join(self.rec_dir, "detections_*.json")):
                os.remove(f)
            for f in glob.glob(os.path.join(self.rec_dir, "detect_*.wav")):
                os.remove(f)
            self.tree.delete(*self.tree.get_children())
            self.status_lbl.config(text="Журнал очищен")

    def _open_file(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        if len(vals) < 4:
            return
        fp = os.path.join(self.rec_dir, vals[3])
        if os.path.exists(fp):
            os.startfile(fp)


if __name__ == "__main__":
    app = App()
    app.mainloop()
