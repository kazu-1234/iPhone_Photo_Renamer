# version: 1.9.3
# -*- coding: utf-8 -*-

import os
import shutil
import tkinter as tk
import threading
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

# --- コンソールウィンドウを非表示にする (Windows用) ---
try:
    import ctypes
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd != 0:
        ctypes.windll.user32.ShowWindow(hwnd, 0)
except Exception:
    pass

# --- 高DPI対応 (Windows向け) ---
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# --- ライブラリのインポート ---
try:
    from PIL import Image, ExifTags
except ImportError:
    Image = None
    ExifTags = None

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HAS_HEIF_LIB = True
except ImportError:
    HAS_HEIF_LIB = False

try:
    import send2trash
except ImportError:
    send2trash = None

class ImageRenamerApp(tk.Tk):
    """
    画像や動画を撮影日時順にリネームし、指定フォルダへコピーするためのGUIアプリケーション
    v1.9.3: 
      - プログレスバーの進捗率表示の不具合を修正 (最大値の設定漏れ修正)
    """
    # 対応する拡張子を定義
    IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.heic', '.tif', '.tiff', '.bmp', '.gif')
    VIDEO_EXTENSIONS = ('.mov', '.mp4', '.m4v', '.avi', '.wmv')

    def __init__(self):
        super().__init__()
        self.title("iPhone写真・動画リネーマー v1.9.3")
        self.geometry("600x800")
        self.minsize(500, 700)
        
        # --- 変数定義 ---
        self.target_files = []
        self.prefix_var = tk.StringVar(value="IMG_")
        self.padding_var = tk.IntVar(value=4)
        self.start_num_var = tk.IntVar(value=1)
        
        self.file_type_var = tk.StringVar(value="media") # 'media', 'image', 'video', 'all'
        
        # クリーンアップ・変換設定
        self.delete_aae_var = tk.BooleanVar(value=True)
        self.prioritize_edited_var = tk.BooleanVar(value=True)
        self.convert_heic_var = tk.BooleanVar(value=False)
        
        self.is_processing = False
        
        # --- UIのセットアップ ---
        self._setup_widgets()

    def _setup_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. ファイル選択フレーム
        selection_frame = ttk.LabelFrame(main_frame, text="ステップ1: 対象の選択", padding="10")
        selection_frame.pack(fill=tk.X, pady=5)
        
        folder_button = ttk.Button(selection_frame, text="フォルダを選択", command=self.select_folder)
        folder_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        files_button = ttk.Button(selection_frame, text="ファイルを選択", command=self.select_files)
        files_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.file_list_label = ttk.Label(main_frame, text="対象ファイル: 0個")
        self.file_list_label.pack(anchor=tk.W, pady=5)

        # 1.5. ファイル種類選択フレーム
        file_type_frame = ttk.LabelFrame(main_frame, text="ステップ1.5: 対象ファイルの種類", padding="10")
        file_type_frame.pack(fill=tk.X, pady=5)
        
        ttk.Radiobutton(file_type_frame, text="画像と動画 (推奨)", variable=self.file_type_var, value="media").grid(row=0, column=0, padx=10, sticky="w")
        ttk.Radiobutton(file_type_frame, text="画像のみ", variable=self.file_type_var, value="image").grid(row=0, column=1, padx=10, sticky="w")
        ttk.Radiobutton(file_type_frame, text="動画のみ", variable=self.file_type_var, value="video").grid(row=0, column=2, padx=10, sticky="w")
        ttk.Radiobutton(file_type_frame, text="すべてのファイル", variable=self.file_type_var, value="all").grid(row=1, column=0, padx=10, sticky="w", pady=(5,0))

        # 2. リネーム設定フレーム
        settings_frame = ttk.LabelFrame(main_frame, text="ステップ2: ファイル名の設定", padding="10")
        settings_frame.pack(fill=tk.X, pady=5)
        settings_frame.columnconfigure(1, weight=1)

        ttk.Label(settings_frame, text="接頭辞:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(settings_frame, textvariable=self.prefix_var).grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Label(settings_frame, text="桁数:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Spinbox(settings_frame, from_=1, to=10, textvariable=self.padding_var).grid(row=1, column=1, sticky=tk.EW, padx=5)
        ttk.Label(settings_frame, text="開始番号:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(settings_frame, textvariable=self.start_num_var).grid(row=2, column=1, sticky=tk.EW, padx=5)
        
        # 2.5 クリーンアップ・変換設定
        cleanup_frame = ttk.LabelFrame(main_frame, text="ステップ2.5: クリーンアップ・変換設定", padding="10")
        cleanup_frame.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(cleanup_frame, text=".AAEファイルをゴミ箱に移動 (iPhoneの編集データ)", variable=self.delete_aae_var).pack(anchor=tk.W)
        ttk.Checkbutton(cleanup_frame, text="編集後の画像 (`IMG_E...`) を優先し、元画像をバックアップ", variable=self.prioritize_edited_var).pack(anchor=tk.W)
        
        heic_frame = ttk.Frame(cleanup_frame)
        heic_frame.pack(anchor=tk.W, pady=(5, 0))
        ttk.Checkbutton(heic_frame, text=".HEIC を .jpg に変換して保存する", variable=self.convert_heic_var).pack(side=tk.LEFT)
        if not HAS_HEIF_LIB:
            ttk.Label(heic_frame, text="(※pillow-heif未検出のため失敗する可能性があります)", foreground="gray", font=("", 8)).pack(side=tk.LEFT, padx=5)

        # 3. 実行ボタン
        self.rename_button = ttk.Button(main_frame, text="名前を変更して新しいフォルダにコピー", command=self.start_rename_process)
        self.rename_button.pack(fill=tk.X, pady=10)
        
        # 4. 進捗表示フレーム
        self.progress_label_var = tk.StringVar()
        progress_label = ttk.Label(main_frame, textvariable=self.progress_label_var)
        progress_label.pack(anchor=tk.W)
        self.progressbar = ttk.Progressbar(main_frame, mode='determinate')
        self.progressbar.pack(fill=tk.X, pady=(0, 5))

        # 5. ログ表示フレーム
        log_frame = ttk.LabelFrame(main_frame, text="ログ", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, height=10, state="disabled", wrap="word")
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # --- GUI更新用メソッド (スレッドセーフ) ---
    def safe_log(self, message):
        self.after(0, self._log, message)

    def safe_update_progress(self, label, current):
        """進捗更新 (最大値は変更せず現在値のみ更新)"""
        self.after(0, self._update_progress, label, current)

    def safe_set_progress_max(self, max_value):
        """プログレスバーの最大値を設定"""
        self.after(0, self._set_progress_max, max_value)

    def safe_reset_progress(self):
        self.after(0, self._reset_progress)
        
    def safe_show_info(self, title, message):
        self.after(0, lambda: messagebox.showinfo(title, message))
        
    def safe_enable_button(self):
        self.after(0, lambda: self.rename_button.config(state="normal"))

    # --- 内部メソッド ---
    def _reset_progress(self):
        self.progress_label_var.set("")
        self.progressbar['value'] = 0
        self.progressbar['maximum'] = 100 # デフォルトに戻す

    def _set_progress_max(self, max_value):
        self.progressbar['maximum'] = max_value

    def _update_progress(self, label, current):
        # 現在値と最大値(Progressbarが保持)を使って表示
        total = self.progressbar['maximum']
        self.progress_label_var.set(f"{label} ({current}/{total})")
        self.progressbar['value'] = current

    def _log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def _get_valid_extensions(self):
        mode = self.file_type_var.get()
        if mode == 'all': return None
        elif mode == 'image': return self.IMAGE_EXTENSIONS
        elif mode == 'video': return self.VIDEO_EXTENSIONS
        else: return self.IMAGE_EXTENSIONS + self.VIDEO_EXTENSIONS

    def _get_file_types_for_dialog(self):
        mode = self.file_type_var.get()
        img_ext_str = ' '.join([f'*{ext}' for ext in self.IMAGE_EXTENSIONS])
        vid_ext_str = ' '.join([f'*{ext}' for ext in self.VIDEO_EXTENSIONS])
        all_ext_str = f"{img_ext_str} {vid_ext_str}"
        
        if mode == 'all': return [("すべてのファイル", "*.*")]
        elif mode == 'image': return [("画像ファイル", img_ext_str), ("すべてのファイル", "*.*")]
        elif mode == 'video': return [("動画ファイル", vid_ext_str), ("すべてのファイル", "*.*")]
        else: return [("メディアファイル", all_ext_str), ("画像ファイル", img_ext_str), ("動画ファイル", vid_ext_str), ("すべてのファイル", "*.*")]

    # --- イベントハンドラ ---
    def select_folder(self):
        if self.is_processing: return
        folder_path = filedialog.askdirectory(title="フォルダを選択してください")
        if not folder_path: return
        
        self.target_files = []
        self._log(f"フォルダ '{os.path.basename(folder_path)}' をスキャン中...")
        
        valid_extensions = self._get_valid_extensions()
        try:
            for filename in os.listdir(folder_path):
                if filename.startswith('.'): continue
                if valid_extensions is None or filename.lower().endswith(valid_extensions):
                    self.target_files.append(os.path.join(folder_path, filename))
        except Exception as e:
            self._log(f"エラー: フォルダの読み込みに失敗しました - {e}")
            return

        self.file_list_label.config(text=f"対象ファイル: {len(self.target_files)}個")
        self._log(f"{len(self.target_files)}個のファイルを検出しました。")

    def select_files(self):
        if self.is_processing: return
        file_paths = filedialog.askopenfilenames(title="ファイルを選択してください", filetypes=self._get_file_types_for_dialog())
        if not file_paths: return
        self.target_files = list(file_paths)
        self.file_list_label.config(text=f"対象ファイル: {len(self.target_files)}個")
        self._log(f"{len(self.target_files)}個のファイルを選択しました。")

    def get_datetime(self, filepath):
        if Image:
            try:
                if filepath.lower().endswith(self.IMAGE_EXTENSIONS):
                    with Image.open(filepath) as img:
                        exif_data = img._getexif()
                        if exif_data and 36867 in exif_data:
                            datetime_str = exif_data[36867]
                            return datetime.strptime(datetime_str, '%Y:%m:%d %H:%M:%S')
            except Exception:
                pass
        try:
            return datetime.fromtimestamp(os.path.getmtime(filepath))
        except OSError:
            return datetime.now()

    def start_rename_process(self):
        if not self.target_files:
            messagebox.showwarning("エラー", "対象のファイルまたはフォルダが選択されていません。")
            return
        
        try:
            prefix = self.prefix_var.get()
            padding = self.padding_var.get()
            start_num = self.start_num_var.get()
        except tk.TclError:
            messagebox.showwarning("エラー", "桁数と開始番号には整数を入力してください。")
            return

        dest_folder = filedialog.askdirectory(title="保存先のフォルダを選択してください")
        if not dest_folder:
            base_dir = os.path.dirname(self.target_files[0])
            dest_folder = os.path.join(base_dir, "renamed_files")
            self._log("保存先が選択されませんでした。出力フォルダを自動作成します。")
            os.makedirs(dest_folder, exist_ok=True)
        
        self.rename_button.config(state="disabled")
        self.is_processing = True
        self.safe_reset_progress()
        
        convert_heic = self.convert_heic_var.get()
        
        thread = threading.Thread(
            target=self.run_rename_thread,
            args=(dest_folder, prefix, padding, start_num, convert_heic),
            daemon=True
        )
        thread.start()

    def run_rename_thread(self, dest_folder, prefix, padding, start_num, convert_heic):
        self.safe_log("="*30 + "\n処理を開始します...")
        self.safe_log(f"保存先フォルダ: {dest_folder}")
        if convert_heic:
            self.safe_log("設定: .HEICファイルを.jpgに変換します")

        files_to_process = list(self.target_files)
        
        # --- IMG_E... ファイルの優先処理 ---
        if self.prioritize_edited_var.get():
            self.safe_log("編集後のファイル (`IMG_E...`) の優先処理を実行します...")
            path_map = {os.path.normcase(p): p for p in files_to_process}
            edited_pairs = {} 

            for filepath in files_to_process:
                directory, filename = os.path.split(filepath)
                basename, ext = os.path.splitext(filename)
                
                if '_E' in basename:
                    try:
                        prefix_part, num_part = basename.split('_E')
                        original_basename = f"{prefix_part}_{num_part}"
                        normcased_original_path = os.path.normcase(os.path.join(directory, original_basename + ext))

                        if normcased_original_path in path_map:
                            original_path = path_map[normcased_original_path]
                            edited_pairs[original_path] = filepath
                    except ValueError: 
                        continue
            
            if edited_pairs:
                backup_dir = os.path.join(dest_folder, "comparison_backup")
                os.makedirs(backup_dir, exist_ok=True)
                for original_path, edited_path in edited_pairs.items():
                    try:
                        shutil.copy2(original_path, backup_dir)
                        shutil.copy2(edited_path, backup_dir)
                    except Exception: pass
                
                originals_to_exclude = set(edited_pairs.keys())
                files_to_process = [f for f in files_to_process if f not in originals_to_exclude]
                self.safe_log(f"{len(originals_to_exclude)}個の元ファイルを除外しました。")

        # --- 日時取得 ---
        total_files = len(files_to_process)
        self.safe_set_progress_max(total_files) # ★ここで最大値を設定
        
        file_info = []
        for i, f in enumerate(files_to_process):
            if i % 10 == 0:
                self.safe_update_progress("ファイル日時を取得中", i + 1)
            dt = self.get_datetime(f)
            file_info.append({'path': f, 'datetime': dt})
        
        file_info.sort(key=lambda x: x['datetime'])
        
        # --- コピー & 変換処理 ---
        total_to_copy = len(file_info)
        self.safe_set_progress_max(total_to_copy) # ★コピー処理開始時に再度最大値を設定(念のため)
        copied_count = 0
        
        for i, info in enumerate(file_info):
            if i % 5 == 0:
                self.safe_update_progress("ファイルを処理中", i + 1)
            
            current_path = info['path']
            root, extension = os.path.splitext(current_path)
            extension_lower = extension.lower()
            
            new_filename_base = f"{prefix}{str(start_num + copied_count).zfill(padding)}"
            is_converted = False
            dest_extension = extension
            
            if convert_heic and extension_lower == '.heic' and Image:
                try:
                    dest_extension = '.jpg'
                    new_name = new_filename_base + dest_extension
                    dest_path = os.path.join(dest_folder, new_name)
                    
                    if os.path.exists(dest_path):
                        self.safe_log(f"[警告] スキップ: '{new_name}' は既に存在します。")
                        continue

                    with Image.open(current_path) as img:
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        exif = img.info.get('exif')
                        if exif:
                            img.save(dest_path, "JPEG", quality=95, exif=exif)
                        else:
                            img.save(dest_path, "JPEG", quality=95)
                            
                    self.safe_log(f"変換成功: '{os.path.basename(current_path)}' -> '{new_name}'")
                    is_converted = True
                    copied_count += 1
                except Exception as e:
                    self.safe_log(f"[変換エラー] 失敗: {e} -> 通常コピーへ")
                    dest_extension = extension
                    is_converted = False

            if not is_converted:
                new_name = new_filename_base + dest_extension
                dest_path = os.path.join(dest_folder, new_name)
                try:
                    if os.path.exists(dest_path):
                        self.safe_log(f"[警告] スキップ: '{new_name}' は既に存在します。")
                        continue
                    shutil.copy2(current_path, dest_path)
                    self.safe_log(f"コピー: '{os.path.basename(current_path)}' -> '{new_name}'")
                    copied_count += 1
                except Exception as e:
                    self.safe_log(f"[エラー] コピー失敗: {e}")
            
            if self.delete_aae_var.get():
                aae_path = root + '.aae'
                if not os.path.exists(aae_path): aae_path = root + '.AAE'
                if os.path.exists(aae_path):
                    try:
                        send2trash.send2trash(aae_path)
                    except: pass

        self.safe_reset_progress()
        self.safe_log(f"処理完了。{copied_count}個のファイルを処理しました。")
        self.safe_show_info("完了", f"処理が完了しました。\n({copied_count}個のファイル)")
        
        self.target_files = []
        self.after(0, lambda: self.file_list_label.config(text="対象ファイル: 0個"))
        self.safe_enable_button()
        self.is_processing = False

def check_libraries():
    missing = []
    if Image is None: missing.append("Pillow")
    if send2trash is None: missing.append("send2trash")
    if missing:
        error_msg = f"以下のライブラリ不足:\n{', '.join(missing)}\n\npip install {' '.join(missing)} を実行してください。"
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("ライブラリ不足", error_msg)
        return False
    return True

if __name__ == '__main__':
    if check_libraries():
        app = ImageRenamerApp()
        app.mainloop()
