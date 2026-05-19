using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Threading.Tasks;
using System.Windows.Forms;
using NAudio.Wave;
using Newtonsoft.Json;
using Vosk;

namespace VoiceMonitor
{
    public static class Program
    {
        [STAThread]
        public static void Main()
        {
            Application.SetHighDpiMode(HighDpiMode.SystemAware);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }

    public class MainForm : Form
    {
        private readonly string _settingsPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "vm_settings.json");
        private readonly string _modelUrl = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip";
        private readonly string _modelDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "model");

        private AppSettings _settings;
        private Model? _voskModel;
        private VoskRecognizer? _recognizer;
        private WaveInEvent? _waveIn;
        private MemoryStream? _recordingStream;
        private bool _isMonitoring;
        private bool _postRecording;
        private int _postChunks;
        private DateTime? _detectionTime;
        private string? _detectedText;

        private Button _btnStart = null!;
        private Button _btnStop = null!;
        private Button _btnSettings = null!;
        private Button _btnOpenFolder = null!;
        private Button _btnClear = null!;
        private DataGridView _grid = null!;
        private ToolStripStatusLabel _statusLabel = null!;
        private StatusStrip _statusBar = null!;
        private string _recordingsDir = "";

        public MainForm()
        {
            LoadSettings();
            InitForm();
            InitUI();
            Shown += async (_, _) => await EnsureModelReady();
        }

        private void LoadSettings()
        {
            if (File.Exists(_settingsPath))
                _settings = JsonConvert.DeserializeObject<AppSettings>(File.ReadAllText(_settingsPath)) ?? new AppSettings();
            else
            {
                _settings = new AppSettings();
                SaveSettings();
            }
            _recordingsDir = _settings.RecordingsDir;
            Directory.CreateDirectory(_recordingsDir);
        }

        private void SaveSettings()
        {
            File.WriteAllText(_settingsPath, JsonConvert.SerializeObject(_settings, Formatting.Indented));
        }

        private void InitForm()
        {
            Text = "VoiceMonitor — Контроль речи";
            Size = new Size(920, 620);
            MinimumSize = new Size(720, 450);
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.FromArgb(24, 24, 37);
            ForeColor = Color.White;
        }

        private void InitUI()
        {
            var topPanel = new Panel { Dock = DockStyle.Top, Height = 56, BackColor = Color.FromArgb(39, 39, 54), Padding = new Padding(12, 8, 12, 8) };

            _btnStart = Btn("▶  Старт", Color.FromArgb(40, 167, 69));
            _btnStart.Click += (_, _) => StartMonitoring();

            _btnStop = Btn("■  Стоп", Color.FromArgb(220, 53, 69));
            _btnStop.Enabled = false;
            _btnStop.Click += (_, _) => StopMonitoring();

            _btnSettings = Btn("⚙ Настройки", Color.FromArgb(108, 92, 231));
            _btnSettings.Click += (_, _) => ShowSettings();

            _btnOpenFolder = Btn("📂 Папка", Color.FromArgb(108, 92, 231));
            _btnOpenFolder.Click += (_, _) => OpenFolder();

            _btnClear = Btn("🗑 Очистить", Color.FromArgb(108, 92, 231));
            _btnClear.Click += (_, _) => ClearLog();

            topPanel.Controls.AddRange(new Control[] { _btnStart, _btnStop, _btnSettings, _btnOpenFolder, _btnClear });
            Controls.Add(topPanel);

            _grid = new DataGridView
            {
                Dock = DockStyle.Fill,
                BackgroundColor = Color.FromArgb(24, 24, 37),
                ForeColor = Color.White,
                RowHeadersVisible = false,
                AllowUserToAddRows = false,
                AllowUserToDeleteRows = false,
                AllowUserToResizeRows = false,
                ReadOnly = true,
                SelectionMode = DataGridViewSelectionMode.FullRowSelect,
                AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill,
                Font = new Font("Segoe UI", 9),
                ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.DisableResizing,
                ColumnHeadersHeight = 32,
                BorderStyle = BorderStyle.None,
                GridColor = Color.FromArgb(49, 50, 68)
            };

            _grid.Columns.Add("col_date", "Дата");
            _grid.Columns.Add("col_time", "Время");
            _grid.Columns.Add("col_text", "Распознанный текст");
            _grid.Columns.Add("col_file", "Файл");

            _grid.Columns["col_date"].Width = 85;
            _grid.Columns["col_time"].Width = 75;
            _grid.Columns["col_text"].Width = 320;

            _grid.DefaultCellStyle.SelectionBackColor = Color.FromArgb(108, 92, 231);
            _grid.DefaultCellStyle.SelectionForeColor = Color.White;
            _grid.ColumnHeadersDefaultCellStyle.BackColor = Color.FromArgb(39, 39, 54);
            _grid.ColumnHeadersDefaultCellStyle.ForeColor = Color.FromArgb(162, 155, 254);
            _grid.ColumnHeadersDefaultCellStyle.Font = new Font("Segoe UI", 9, FontStyle.Bold);
            _grid.EnableHeadersVisualStyles = false;
            _grid.DoubleClick += Grid_DoubleClick;

            var gridPanel = new Panel { Dock = DockStyle.Fill, Padding = new Padding(12) };
            gridPanel.Controls.Add(_grid);
            Controls.Add(gridPanel);

            _statusBar = new StatusStrip { BackColor = Color.FromArgb(24, 24, 37), ForeColor = Color.White };
            _statusLabel = new ToolStripStatusLabel("Готово") { ForeColor = Color.FromArgb(162, 155, 254) };
            _statusBar.Items.Add(_statusLabel);
            Controls.Add(_statusBar);

            LoadDetectionLog();
        }

        private Button Btn(string text, Color color)
        {
            return new Button
            {
                Text = text,
                Size = new Size(90, 40),
                BackColor = color,
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                Cursor = Cursors.Hand
            };
        }

        private async Task EnsureModelReady()
        {
            if (Directory.Exists(_modelDir) && Directory.GetFiles(_modelDir, "*", SearchOption.AllDirectories).Length > 5)
            {
                LoadModel();
                return;
            }

            if (MessageBox.Show("Модель распознавания речи не найдена.\nСкачать (~50 MB)?", "VoiceMonitor", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
            {
                await DownloadModel();
            }
        }

        private async Task DownloadModel()
        {
            _statusLabel.Text = "Скачивание модели...";
            _statusLabel.ForeColor = Color.FromArgb(255, 193, 7);
            _btnStart.Enabled = false;

            var zipPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "model_temp.zip");

            try
            {
                using var client = new HttpClient { Timeout = TimeSpan.FromMinutes(15) };
                using var response = await client.GetAsync(_modelUrl);
                response.EnsureSuccessStatusCode();

                var total = response.Content.Headers.ContentLength ?? 0;
                var downloaded = 0L;
                var buf = new byte[81920];

                await using (var fs = new FileStream(zipPath, FileMode.Create, FileAccess.Write, FileShare.None))
                await using (var stream = await response.Content.ReadAsStreamAsync())
                {
                    while (true)
                    {
                        var n = await stream.ReadAsync(buf);
                        if (n == 0) break;
                        await fs.WriteAsync(buf.AsMemory(0, n));
                        downloaded += n;
                        if (total > 0) Invoke(() => _statusLabel.Text = $"Скачивание: {downloaded * 100 / total}%");
                    }
                }

                Invoke(() => _statusLabel.Text = "Распаковка...");
                System.IO.Compression.ZipFile.ExtractToDirectory(zipPath, _modelDir, true);
                File.Delete(zipPath);

                // Перемещаем из вложенной папки
                var inner = Directory.GetDirectories(_modelDir).FirstOrDefault();
                if (inner != null)
                {
                    foreach (var d in Directory.GetDirectories(inner, "*", SearchOption.AllDirectories))
                        Directory.CreateDirectory(d.Replace(inner, _modelDir));
                    foreach (var f in Directory.GetFiles(inner, "*", SearchOption.AllDirectories))
                        File.Move(f, f.Replace(inner, _modelDir), true);
                    Directory.Delete(inner, true);
                }

                LoadModel();
                _statusLabel.Text = "Модель загружена. Нажмите «Старт».";
                _statusLabel.ForeColor = Color.FromArgb(40, 167, 69);
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Ошибка: {ex.Message}", "Ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error);
                _statusLabel.Text = "Ошибка загрузки модели";
                _statusLabel.ForeColor = Color.FromArgb(220, 53, 69);
            }
            finally { _btnStart.Enabled = true; }
        }

        private void LoadModel()
        {
            try
            {
                _voskModel = new Model(_modelDir);
                _recognizer = new VoskRecognizer(_voskModel, 16000);
                _recognizer.SetWords(true);
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Ошибка модели: {ex.Message}", "Ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void StartMonitoring()
        {
            if (_voskModel == null) { MessageBox.Show("Модель не загружена.", "Ошибка", MessageBoxButtons.OK, MessageBoxIcon.Warning); return; }

            try
            {
                _waveIn = new WaveInEvent { WaveFormat = new WaveFormat(16000, 1), BufferMilliseconds = 200 };
                _waveIn.DataAvailable += OnAudio;
                _waveIn.StartRecording();

                _recordingStream = new MemoryStream();
                _isMonitoring = true;
                _postRecording = false;
                _postChunks = 0;

                _btnStart.Enabled = false;
                _btnStop.Enabled = true;
                _statusLabel.Text = "● Мониторинг активен";
                _statusLabel.ForeColor = Color.FromArgb(40, 167, 69);
            }
            catch (Exception ex) { MessageBox.Show($"Ошибка: {ex.Message}", "Ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error); }
        }

        private void StopMonitoring()
        {
            _isMonitoring = false;
            _waveIn?.StopRecording();
            _waveIn?.Dispose();
            _waveIn = null;
            _btnStart.Enabled = true;
            _btnStop.Enabled = false;
            _statusLabel.Text = "Готово";
            _statusLabel.ForeColor = Color.FromArgb(162, 155, 254);
        }

        private void OnAudio(object? sender, WaveInEventArgs e)
        {
            if (!_isMonitoring) return;

            _recognizer?.AcceptWaveform(e.Buffer, e.BytesRecorded);

            if (_postRecording)
            {
                _recordingStream?.Write(e.Buffer, 0, e.BytesRecorded);
                if (++_postChunks >= _settings.PostRecordChunks) { SaveRecording(); _postRecording = false; _postChunks = 0; }
                return;
            }

            _recordingStream?.Write(e.Buffer, 0, e.BytesRecorded);

            var result = _recognizer?.Result();
            if (!string.IsNullOrEmpty(result))
            {
                var j = JsonConvert.DeserializeObject<VoskResult>(result);
                if (j?.Text != null && HasProfanity(j.Text))
                {
                    _detectionTime = DateTime.Now;
                    _detectedText = j.Text;
                    _postRecording = true;
                    _postChunks = 0;
                }
            }
        }

        private void SaveRecording()
        {
            if (_recordingStream == null || _recordingStream.Length == 0) return;
            try
            {
                var ts = DateTime.Now.ToString("yyyy-MM-dd_HH-mm-ss");
                var file = $"detect_{ts}.wav";
                var path = Path.Combine(_recordingsDir, file);

                _recordingStream.Position = 0;
                var raw = _recordingStream.ToArray();
                using var w = new WaveFileWriter(path, new WaveFormat(16000, 1));
                w.Write(raw, 0, raw.Length);

                var entry = new DetectionEntry { Date = _detectionTime?.ToString("dd.MM.yyyy") ?? "", Time = _detectionTime?.ToString("HH:mm:ss") ?? "", Text = _detectedText ?? "", File = file };
                var logPath = Path.Combine(_recordingsDir, $"detections_{DateTime.Now:yyyy-MM}.json");
                var entries = File.Exists(logPath) ? JsonConvert.DeserializeObject<List<DetectionEntry>>(File.ReadAllText(logPath)) ?? new List<DetectionEntry>() : new List<DetectionEntry>();
                entries.Add(entry);
                File.WriteAllText(logPath, JsonConvert.SerializeObject(entries, Formatting.Indented));

                Invoke(() => { _grid.Rows.Add(entry.Date, entry.Time, entry.Text, entry.File); _statusLabel.Text = $"Детекция: {entry.Time} — {entry.Text}"; });

                _recordingStream.Dispose();
                _recordingStream = new MemoryStream();
            }
            catch { }
        }

        private bool HasProfanity(string text) => _settings.ProfanityWords.Any(w => text.ToLower().Contains(w));

        private void LoadDetectionLog()
        {
            _grid.Rows.Clear();
            if (!Directory.Exists(_recordingsDir)) return;
            foreach (var f in Directory.GetFiles(_recordingsDir, "detections_*.json").OrderByDescending(x => x).Take(10))
            {
                try
                {
                    var entries = JsonConvert.DeserializeObject<List<DetectionEntry>>(File.ReadAllText(f));
                    if (entries != null) foreach (var e in entries.OrderByDescending(x => x.Time)) _grid.Rows.Add(e.Date, e.Time, e.Text, e.File);
                }
                catch { }
            }
        }

        private void Grid_DoubleClick(object? sender, EventArgs e)
        {
            if (_grid.CurrentRow?.Cells["col_file"].Value?.ToString() is not { } f) return;
            var path = Path.Combine(_recordingsDir, f);
            if (File.Exists(path)) System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo { FileName = path, UseShellExecute = true });
        }

        private void ShowSettings()
        {
            using var dlg = new SettingsForm(_settings, _modelDir);
            if (dlg.ShowDialog() == DialogResult.OK) { _settings = dlg.Settings; SaveSettings(); _recordingsDir = _settings.RecordingsDir; Directory.CreateDirectory(_recordingsDir); }
        }

        private void OpenFolder() { if (Directory.Exists(_recordingsDir)) System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo { FileName = _recordingsDir, UseShellExecute = true }); }

        private void ClearLog()
        {
            if (MessageBox.Show("Удалить все записи?", "Подтверждение", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
            {
                foreach (var f in Directory.GetFiles(_recordingsDir, "detections_*.json")) File.Delete(f);
                foreach (var f in Directory.GetFiles(_recordingsDir, "detect_*.wav")) File.Delete(f);
                _grid.Rows.Clear();
                _statusLabel.Text = "Журнал очищен";
            }
        }
    }

    public class AppSettings
    {
        public string RecordingsDir { get; set; } = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "recordings");
        public List<string> ProfanityWords { get; set; } = new() { "блять", "блядь", "бля", "сука", "хуй", "хуя", "хуе", "пизд", "пиздец", "ебат", "ебан", "ебать", "нахуй", "похуй", "заеб", "уеб", "отъеб", "долбоёб", "долбоеб", "мудак", "мудила", "залуп", "шлюх", "пидор", "еблан", "дебил", "чмо", "лох", "гандон", "гондон", "говно", "жопа" };
        public int PostRecordChunks { get; set; } = 15;
    }

    public class DetectionEntry
    {
        public string Date { get; set; } = "";
        public string Time { get; set; } = "";
        public string Text { get; set; } = "";
        public string File { get; set; } = "";
    }

    public class VoskResult
    {
        [JsonProperty("text")] public string? Text { get; set; }
    }
}
