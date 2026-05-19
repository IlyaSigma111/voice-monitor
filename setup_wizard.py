import os
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "recordings_dir": "recordings",
    "setup_complete": False,
    "first_run": True,
}


def load_settings():
    settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGS_FILE)
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGS_FILE)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def get_recordings_dir():
    settings = load_settings()
    return settings.get("recordings_dir", "recordings")


def is_setup_complete():
    settings = load_settings()
    return settings.get("setup_complete", False)


class SetupWizard:
    def __init__(self, root):
        self.root = root
        self.root.title("VoiceMonitor — Настройка")
        self.root.geometry("520x420")
        self.root.resizable(False, False)

        self.root.configure(bg="#0a0a0f")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#0a0a0f")
        style.configure("TLabel", background="#0a0a0f", foreground="#ffffff", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#0a0a0f", foreground="#a29bfe", font=("Segoe UI", 14, "bold"))
        style.configure("Subtitle.TLabel", background="#0a0a0f", foreground="#a0a0b0", font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=(20, 8))
        style.configure("Accent.TButton", background="#6c5ce7", foreground="#ffffff", font=("Segoe UI", 10, "bold"))

        self._build_ui()
        self._center_window()

    def _center_window(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        main = ttk.Frame(self.root, padding="32")
        main.pack(fill="both", expand=True)

        logo_label = ttk.Label(main, text="VoiceMonitor", style="Title.TLabel")
        logo_label.pack(anchor="w", pady=(0, 4))

        ttk.Label(main, text="Добро пожаловать! Выполняется первый запуск.", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 20))

        ttk.Label(main, text="Куда сохранять записанные фрагменты?", style="TLabel").pack(anchor="w", pady=(0, 12))

        self._var = tk.StringVar(value="default")

        options = [
            ("default", 'Папка рядом с программой (рекомендуется)'),
            ("documents", 'Мои документы \\ VoiceMonitor'),
            ("desktop", 'Рабочий стол \\ VoiceMonitor'),
            ("custom", 'Выбрать свою папку...'),
        ]

        for value, text in options:
            rb = ttk.Radiobutton(main, text=text, variable=self._var, value=value, style="TLabel")
            rb.pack(anchor="w", pady=2)

        self._custom_frame = ttk.Frame(main)
        self._custom_frame.pack(fill="x", pady=(4, 16), padx=(24, 0))
        self._custom_frame.pack_forget()

        self._custom_path = tk.StringVar()
        self._entry = ttk.Entry(self._custom_frame, textvariable=self._custom_path, state="disabled")
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self._browse_btn = ttk.Button(self._custom_frame, text="Обзор...", command=self._browse)
        self._browse_btn.pack(side="right")

        self._var.trace_add("write", self._on_radio_change)

        sep = ttk.Separator(main, orient="horizontal")
        sep.pack(fill="x", pady=12)

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill="x")

        self._apply_btn = ttk.Button(btn_frame, text="Сохранить и начать", style="Accent.TButton", command=self._apply)
        self._apply_btn.pack(side="right")

        note_label = ttk.Label(main, text="Настройки можно изменить позже в settings.json", style="Subtitle.TLabel")
        note_label.pack(anchor="w", pady=(8, 0))

    def _on_radio_change(self, *args):
        if self._var.get() == "custom":
            self._custom_frame.pack(fill="x", pady=(4, 16), padx=(24, 0))
            self._entry.config(state="normal")
        else:
            self._custom_frame.pack_forget()

    def _browse(self):
        folder = filedialog.askdirectory(title="Выберите папку для записей")
        if folder:
            self._custom_path.set(folder)

    def _get_path(self):
        choice = self._var.get()
        if choice == "default":
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordings")
        elif choice == "documents":
            docs = os.path.expanduser("~/Documents")
            return os.path.join(docs, "VoiceMonitor")
        elif choice == "desktop":
            desk = os.path.expanduser("~/Desktop")
            return os.path.join(desk, "VoiceMonitor")
        else:
            custom = self._custom_path.get().strip()
            return custom if custom else None

    def _apply(self):
        path = self._get_path()
        if not path:
            messagebox.showwarning("Внимание", "Выберите или введите путь для сохранения записей.")
            return

        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать папку:\n{e}")
            return

        settings = {
            "recordings_dir": path,
            "setup_complete": True,
            "first_run": False,
        }
        save_settings(settings)

        messagebox.showinfo("Готово", f"Записи будут сохраняться в:\n{path}")
        self.root.destroy()


def run_setup():
    root = tk.Tk()
    wizard = SetupWizard(root)
    root.mainloop()
