# version: 1.9.0
# -*- coding: utf-8 -*-

import os
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

# --- 高DPI対応 (Windows向け) ---
# GUIがぼやけないように、Windowsに対してDPI AWARENESSを設定する
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except ImportError:
    # Windows以外のOSでは何もしない
    pass
except Exception:
    # その他のエラーが発生した場合も無視する
    pass

# --- ライブラリのインポートを試みる ---
try:
    from PIL import Image, ExifTags
except ImportError:
    Image = None
    ExifTags = None

try:
    import send2trash
except ImportError:
    send2trash = None

class ImageRenamerApp(tk.Tk):
    """
    画像や動画を撮影日時順にリネームし、指定フォルダへコピーするためのGUIアプリケーション
    """
    # 対応する拡張子を定義
    IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.heic', '.tif', '.tiff')
    VIDEO_EXTENSIONS = ('.mov', '.mp4', '.m4v')

    def __init__(self):
        super().__init__()
        self.title("iPhone写真・動画リネーマー")
        self.geometry("600x750") # ウィンドウの高さを拡大
        self.minsize(500, 640)
        
        # --- 変数定義 ---
        self.target_files = []
        self.prefix_var = tk.StringVar(value="IMG_")
        self.padding_var = tk.IntVar(value=4)
        self.start_num_var = tk.IntVar(value=1)
        self.file_type_var = tk.StringVar(value="all") # 'all', 'image', 'video'
        self.delete_aae_var = tk.BooleanVar(value=True)
        self.prioritize_edited_var = tk.BooleanVar(value=True) # E付き画像優先フラグ
        
        # --- UIのセットアップ ---
        self._setup_widgets()

    def _setup_widgets(self):
        """GUIウィジェットの作成と配置"""
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
        
        ttk.Radiobutton(file_type_frame, text="画像と動画", variable=self.file_type_var, value="all").pack(side=tk.LEFT, padx=10, pady=2)
        ttk.Radiobutton(file_type_frame, text="画像のみ", variable=self.file_type_var, value="image").pack(side=tk.LEFT, padx=10, pady=2)
        ttk.Radiobutton(file_type_frame, text="動画のみ", variable=self.file_type_var, value="video").pack(side=tk.LEFT, padx=10, pady=2)

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
        
        # 2.5 クリーンアップ設定
        cleanup_frame = ttk.LabelFrame(main_frame, text="ステップ2.5: クリーンアップ設定", padding="10")
        cleanup_frame.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(cleanup_frame, text=".AAEファイルをゴミ箱に移動する (元のファイルの関連)", variable=self.delete_aae_var).pack(anchor=tk.W)
        ttk.Checkbutton(cleanup_frame, text="編集後の画像 (`IMG_E...`) を優先し、元画像をバックアップ", variable=self.prioritize_edited_var).pack(anchor=tk.W)

        # 3. 実行ボタン
        self.rename_button = ttk.Button(main_frame, text="名前を変更して新しいフォルダにコピー", command=self.rename_files)
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

    def _reset_progress(self):
        """プログレスバーとラベルをリセットする"""
        self.progress_label_var.set("")
        self.progressbar['value'] = 0
        self.update_idletasks()

    def _update_progress(self, label, current, total):
        """プログレスバーとラベルを更新する"""
        self.progress_label_var.set(f"{label} ({current}/{total})")
        self.progressbar['value'] = current
        self.update_idletasks()

    def _log(self, message):
        """ログエリアにメッセージを追記する"""
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.update_idletasks()

    def _get_valid_extensions(self):
        """選択モードに基づいて有効な拡張子のタプルを返す"""
        mode = self.file_type_var.get()
        if mode == 'image': return self.IMAGE_EXTENSIONS
        elif mode == 'video': return self.VIDEO_EXTENSIONS
        else: return self.IMAGE_EXTENSIONS + self.VIDEO_EXTENSIONS

    def _get_file_types_for_dialog(self):
        """ファイル選択ダイアログ用のファイルタイプ情報を生成する"""
        mode = self.file_type_var.get()
        img_ext_str = ' '.join([f'*{ext}' for ext in self.IMAGE_EXTENSIONS])
        vid_ext_str = ' '.join([f'*{ext}' for ext in self.VIDEO_EXTENSIONS])
        all_ext_str = f"{img_ext_str} {vid_ext_str}"
        
        if mode == 'image': return [("画像ファイル", img_ext_str), ("すべてのファイル", "*.*")]
        elif mode == 'video': return [("動画ファイル", vid_ext_str), ("すべてのファイル", "*.*")]
        else: return [("メディアファイル", all_ext_str), ("画像ファイル", img_ext_str), ("動画ファイル", vid_ext_str), ("すべてのファイル", "*.*")]

    def select_folder(self):
        """フォルダ選択ダイアログを開き、対象ファイルを取得する"""
        folder_path = filedialog.askdirectory(title="フォルダを選択してください")
        if not folder_path: return
        self.target_files = []
        self._log(f"フォルダ '{os.path.basename(folder_path)}' をスキャン中...")
        valid_extensions = self._get_valid_extensions()
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(valid_extensions):
                self.target_files.append(os.path.join(folder_path, filename))
        self.file_list_label.config(text=f"対象ファイル: {len(self.target_files)}個")
        self._log(f"{len(self.target_files)}個のファイルを検出しました。")

    def select_files(self):
        """ファイル選択ダイアログを開き、対象ファイルを取得する"""
        file_paths = filedialog.askopenfilenames(title="ファイルを選択してください", filetypes=self._get_file_types_for_dialog())
        if not file_paths: return
        self.target_files = list(file_paths)
        self.file_list_label.config(text=f"対象ファイル: {len(self.target_files)}個")
        self._log(f"{len(self.target_files)}個のファイルを選択しました。")

    def get_datetime(self, filepath):
        """画像のExif情報から撮影日時を取得する。なければファイルの更新日時を返す"""
        if Image:
            try:
                with Image.open(filepath) as img:
                    exif_data = img._getexif()
                    if exif_data and 36867 in exif_data:
                        datetime_str = exif_data[36867]
                        return datetime.strptime(datetime_str, '%Y:%m:%d %H:%M:%S')
            except Exception: pass
        return datetime.fromtimestamp(os.path.getmtime(filepath))

    def rename_files(self):
        """ファイルのリネーム処理をコピー方式で実行する"""
        if not self.target_files:
            messagebox.showwarning("エラー", "対象のファイルまたはフォルダが選択されていません。")
            return
        
        try:
            prefix, padding, start_num = self.prefix_var.get(), self.padding_var.get(), self.start_num_var.get()
        except tk.TclError:
            messagebox.showwarning("エラー", "桁数と開始番号には整数を入力してください。")
            return

        # --- 保存先のフォルダを選択、未選択なら自動作成 ---
        dest_folder = filedialog.askdirectory(title="保存先のフォルダを選択してください")
        if not dest_folder:
            base_dir = os.path.dirname(self.target_files[0])
            dest_folder = os.path.join(base_dir, "renamed_photos")
            self._log("保存先が選択されませんでした。出力フォルダを自動作成します。")
            os.makedirs(dest_folder, exist_ok=True)
        
        self.rename_button.config(state="disabled") # 処理中にボタンを無効化
        self._reset_progress()

        self._log("="*30 + "\n処理を開始します...")
        self._log(f"保存先フォルダ: {dest_folder}")

        files_to_process = list(self.target_files)
        
        # --- IMG_E... ファイルの優先処理 (不具合修正版) ---
        if self.prioritize_edited_var.get():
            self._log("編集後のファイル (`IMG_E...`) の優先処理を実行します...")
            
            # OSのパス形式（大文字/小文字, 区切り文字）の違いを吸収するためのマップ
            path_map = {os.path.normcase(p): p for p in files_to_process}
            edited_pairs = {} # key: original_path, value: edited_path

            for filepath in files_to_process:
                directory, filename = os.path.split(filepath)
                basename, ext = os.path.splitext(filename)
                
                # `_E` を含むファイル名をチェック
                if '_E' in basename:
                    try:
                        prefix_part, num_part = basename.split('_E')
                        original_basename = f"{prefix_part}_{num_part}"
                        
                        # 推測した元のファイルパスを正規化して比較
                        normcased_original_path = os.path.normcase(os.path.join(directory, original_basename + ext))

                        # 正規化されたパスがマップに存在するかチェック
                        if normcased_original_path in path_map:
                            original_path = path_map[normcased_original_path]
                            edited_pairs[original_path] = filepath
                    except ValueError: 
                        continue # `split` に失敗した場合はスキップ
            
            if edited_pairs:
                backup_dir = os.path.join(dest_folder, "comparison_backup")
                os.makedirs(backup_dir, exist_ok=True)
                self._log(f"比較用バックアップフォルダを作成/確認しました: {backup_dir}")

                for original_path, edited_path in edited_pairs.items():
                    try:
                        shutil.copy2(original_path, backup_dir)
                        self._log(f"  - バックアップ (元): '{os.path.basename(original_path)}'")
                        shutil.copy2(edited_path, backup_dir)
                        self._log(f"  - バックアップ (編集後): '{os.path.basename(edited_path)}'")
                    except Exception as e:
                        self._log(f"  - [エラー] '{os.path.basename(original_path)}' ペアのバックアップに失敗: {e}")
                
                originals_to_exclude = set(edited_pairs.keys())
                files_to_process = [f for f in files_to_process if f not in originals_to_exclude]
                self._log(f"{len(originals_to_exclude)}個の元ファイルを処理対象から除外しました。")

        # --- ファイルの日時取得 ---
        file_info = []
        total_files = len(files_to_process)
        self.progressbar['maximum'] = total_files
        for i, f in enumerate(files_to_process):
            self._update_progress("ファイル日時を取得中", i + 1, total_files)
            dt = self.get_datetime(f)
            file_info.append({'path': f, 'datetime': dt})
        
        file_info.sort(key=lambda x: x['datetime'])
        
        # --- コピー処理 ---
        total_to_copy = len(file_info)
        self.progressbar['maximum'] = total_to_copy
        copied_count = 0
        for i, info in enumerate(file_info):
            self._update_progress("ファイルをコピー中", i + 1, total_to_copy)
            current_path = info['path']
            
            extension = os.path.splitext(current_path)[1]
            new_name = f"{prefix}{str(start_num + copied_count).zfill(padding)}{extension}"
            dest_path = os.path.join(dest_folder, new_name)
            
            try:
                if os.path.exists(dest_path):
                    self._log(f"[警告] スキップ: '{new_name}' は保存先に既に存在します。")
                    continue
                
                shutil.copy2(current_path, dest_path)
                self._log(f"'{os.path.basename(current_path)}' -> '{new_name}' としてコピーしました。")
                
                # .AAEファイルの処理 (元のファイルの関連ファイルをゴミ箱へ)
                if self.delete_aae_var.get():
                    base_name, _ = os.path.splitext(current_path)
                    aae_path = base_name + '.aae'
                    if not os.path.exists(aae_path): aae_path = base_name + '.AAE'
                    if os.path.exists(aae_path):
                        try:
                            send2trash.send2trash(aae_path)
                            self._log(f"  └ 関連ファイル '{os.path.basename(aae_path)}' をゴミ箱に移動。")
                        except Exception as e:
                            self._log(f"  └ [エラー] '{os.path.basename(aae_path)}' の移動に失敗: {e}")
                
                copied_count += 1
            except Exception as e:
                self._log(f"[エラー] '{os.path.basename(current_path)}' のコピー中にエラーが発生: {e}")

        self._reset_progress()
        self._log(f"処理完了。{copied_count}個のファイルをコピーしました。")
        messagebox.showinfo("完了", f"処理が完了しました。\n({copied_count}個のファイルを指定のフォルダにコピーしました)")
        self.target_files = []
        self.file_list_label.config(text="対象ファイル: 0個")
        self.rename_button.config(state="normal")


def check_libraries():
    """実行に必要なライブラリがインストールされているか確認する"""
    missing = []
    if Image is None: missing.append("Pillow")
    if send2trash is None: missing.append("send2trash")
    
    if missing:
        error_msg = f"以下のライブラリが見つかりません:\n{', '.join(missing)}\n\n"
        error_msg += "お手数ですが、コマンドプロンプトやターミナルを開き、\n"
        for lib in missing:
            error_msg += f"pip install {lib}\n"
        error_msg += "と入力してインストールしてください。"
        
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("ライブラリ不足", error_msg)
        return False
    return True

if __name__ == '__main__':
    if check_libraries():
        app = ImageRenamerApp()
        app.mainloop()

