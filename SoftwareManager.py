import os
import sys
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import shutil


class SoftwareManager:
    def __init__(self, root):
        self.root = root
        self.root.title("U盘软件库管理器")
        self.root.geometry("820x600")
        self.root.minsize(700, 500)

        # 使用系统默认字体，这里设置常见的Windows字体
        self.set_default_font()

        self.usb_drive = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.software_dir = os.path.join(self.usb_drive, "Software")
        self.db_path = os.path.join(self.usb_drive, "software.db")

        if not os.path.exists(self.software_dir):
            os.makedirs(self.software_dir)

        self.initialize_database()
        self.create_ui()

        self.sort_ascending = True  # 软件名称排序顺序，默认升序

        self.refresh_tags_ui()
        self.refresh_software_list()

    def set_default_font(self):
        style = ttk.Style()
        style.configure("TLabel", font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", font=("Segoe UI", 9))

    def initialize_database(self):
        first_init = not os.path.exists(self.db_path)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''CREATE TABLE IF NOT EXISTS software (
                          id INTEGER PRIMARY KEY,
                          name TEXT NOT NULL,
                          filename TEXT NOT NULL,
                          path TEXT UNIQUE NOT NULL,
                          description TEXT DEFAULT '',
                          last_used TEXT,
                          use_count INTEGER DEFAULT 0
                        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS tags (
                          id INTEGER PRIMARY KEY,
                          name TEXT UNIQUE NOT NULL
                        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS software_tags (
                          software_id INTEGER NOT NULL,
                          tag_id INTEGER NOT NULL,
                          PRIMARY KEY (software_id, tag_id),
                          FOREIGN KEY (software_id) REFERENCES software(id),
                          FOREIGN KEY (tag_id) REFERENCES tags(id)
                        )''')

        if first_init:
            default_tags = ["必备", "驱动", "办公", "浏览器", "工具", "安全", "系统"]
            for tag in default_tags:
                try:
                    cursor.execute("INSERT INTO tags (name) VALUES (?)", (tag,))
                except sqlite3.IntegrityError:
                    pass

        conn.commit()
        conn.close()

    def create_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.software_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.software_tab, text="软件列表")

        self.tags_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.tags_tab, text="标签管理")

        self.build_software_tab()
        self.build_tags_tab()

        self.status_var = tk.StringVar()
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=(5, 2))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.update_status("就绪")

    def build_software_tab(self):
        toolbar = ttk.Frame(self.software_tab)
        toolbar.pack(fill=tk.X, pady=(0, 10))

        refresh_btn = ttk.Button(toolbar, text="刷新列表", command=self.refresh_software_list)
        refresh_btn.pack(side=tk.LEFT, padx=5)

        add_btn = ttk.Button(toolbar, text="添加软件", command=self.add_software)
        add_btn.pack(side=tk.LEFT, padx=5)

        filter_outer_frame = ttk.LabelFrame(toolbar, text="标签过滤")
        filter_outer_frame.pack(side=tk.LEFT, padx=10, pady=2, fill=tk.X, expand=True)

        canvas = tk.Canvas(filter_outer_frame, height=40, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)

        h_scroll = ttk.Scrollbar(filter_outer_frame, orient="horizontal", command=canvas.xview)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        canvas.configure(xscrollcommand=h_scroll.set)

        self.tag_filter_frame = ttk.Frame(canvas)
        self.tag_filter_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.tag_filter_frame, anchor="nw")

        self.all_tags = self.get_all_tags()
        self.tag_vars = {}
        for tag in self.all_tags:
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(self.tag_filter_frame, text=tag, variable=var, command=self.refresh_software_list)
            cb.pack(side=tk.LEFT, padx=4, pady=5)
            self.tag_vars[tag] = var

        all_btn = ttk.Button(filter_outer_frame, text="全部", command=self.clear_tag_filter)
        all_btn.pack(side=tk.LEFT, padx=5, pady=2)

        search_frame = ttk.Frame(toolbar)
        search_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT, padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.refresh_software_list())
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        list_frame = ttk.Frame(self.software_tab)
        list_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("name", "description", "tags")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("name", text="软件名称", command=self.toggle_sort_name)
        self.tree.heading("description", text="功能描述")
        self.tree.heading("tags", text="标签")

        self.tree.column("name", width=220, anchor="w")
        self.tree.column("description", width=360)
        self.tree.column("tags", width=160, anchor="center")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self.on_software_select)
        self.tree.bind("<Double-1>", self.on_software_double_click)

        detail_frame = ttk.LabelFrame(self.software_tab, text="详细信息")
        detail_frame.pack(fill=tk.X, pady=(10, 0))

        labels = ["名称:", "路径:", "描述:", "标签:"]
        self.detail_vars = {}
        for i, label_text in enumerate(labels):
            ttk.Label(detail_frame, text=label_text).grid(row=i, column=0, sticky=tk.W, padx=5, pady=2)
            var = tk.StringVar()
            ttk.Label(detail_frame, textvariable=var).grid(row=i, column=1, sticky=tk.W, padx=5, pady=2)
            self.detail_vars[label_text[:-1]] = var

        btn_frame = ttk.Frame(detail_frame)
        btn_frame.grid(row=len(labels), column=0, columnspan=2, pady=8)

        self.run_btn = ttk.Button(btn_frame, text="运行", command=self.run_selected_software)
        self.run_btn.pack(side=tk.LEFT, padx=8)

        self.edit_btn = ttk.Button(btn_frame, text="编辑", command=self.edit_software)
        self.edit_btn.pack(side=tk.LEFT, padx=8)

        self.manage_tags_btn = ttk.Button(btn_frame, text="管理标签", command=self.manage_tags_for_selected)
        self.manage_tags_btn.pack(side=tk.LEFT, padx=8)

        self.run_btn.config(state=tk.DISABLED)
        self.edit_btn.config(state=tk.DISABLED)
        self.manage_tags_btn.config(state=tk.DISABLED)

        self.selected_software_id = None

    def build_tags_tab(self):
        left_frame = ttk.Frame(self.tags_tab)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        ttk.Label(left_frame, text="软件列表").pack(anchor=tk.W, padx=3)

        self.tags_software_list = tk.Listbox(left_frame, selectmode=tk.SINGLE)
        self.tags_software_list.pack(fill=tk.BOTH, expand=True, pady=5)
        self.tags_software_list.bind("<<ListboxSelect>>", self.on_tags_software_select)

        right_frame = ttk.Frame(self.tags_tab)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        tags_frame = ttk.LabelFrame(right_frame, text="标签管理")
        tags_frame.pack(fill=tk.X, pady=5)

        add_frame = ttk.Frame(tags_frame)
        add_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(add_frame, text="新标签:").pack(side=tk.LEFT)
        self.new_tag_var = tk.StringVar()
        new_tag_entry = ttk.Entry(add_frame, textvariable=self.new_tag_var, width=20)
        new_tag_entry.pack(side=tk.LEFT, padx=5)

        add_tag_btn = ttk.Button(add_frame, text="添加", command=self.add_new_tag)
        add_tag_btn.pack(side=tk.LEFT)

        delete_frame = ttk.Frame(tags_frame)
        delete_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(delete_frame, text="删除标签:").pack(side=tk.LEFT)
        self.delete_tag_var = tk.StringVar()
        self.delete_tag_combo = ttk.Combobox(delete_frame, textvariable=self.delete_tag_var, state="readonly", width=18)
        self.delete_tag_combo.pack(side=tk.LEFT, padx=5)

        delete_tag_btn = ttk.Button(delete_frame, text="删除", command=self.delete_tag)
        delete_tag_btn.pack(side=tk.LEFT)

        assign_frame = ttk.LabelFrame(right_frame, text="标签分配")
        assign_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        ttk.Label(assign_frame, text="当前标签:").pack(anchor=tk.W, padx=5, pady=2)
        self.current_tags_var = tk.StringVar()
        ttk.Label(assign_frame, textvariable=self.current_tags_var, foreground="blue").pack(anchor=tk.W, padx=5, pady=2)

        ttk.Label(assign_frame, text="可用标签:").pack(anchor=tk.W, padx=5, pady=5)

        self.tags_buttons_frame = ttk.Frame(assign_frame)
        self.tags_buttons_frame.pack(fill=tk.X, padx=5, pady=5)

        btn_frame = ttk.Frame(assign_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        save_btn = ttk.Button(btn_frame, text="保存更改", command=self.save_tags_changes)
        save_btn.pack(pady=5)

        self.current_tags_var.set("无")
        self.selected_tags = set()
        self.current_software_id = None

    def toggle_sort_name(self):
        self.sort_ascending = not getattr(self, "sort_ascending", True)
        self.refresh_software_list()

    def refresh_software_list(self):
        self.scan_software_directory()

        for item in self.tree.get_children():
            self.tree.delete(item)

        search_text = self.search_var.get().strip().lower()
        active_tags = [tag for tag, var in self.tag_vars.items() if var.get()]

        software_list = self.get_software_list(search_text, active_tags)

        software_list.sort(key=lambda x: x[1].lower(), reverse=not self.sort_ascending)

        for sw in software_list:
            tags = self.get_tags_for_software(sw[0])
            self.tree.insert("", "end", values=(
                sw[1],
                sw[4],
                ", ".join(tags)
            ), iid=f"sw_{sw[0]}")

        self.update_status(f"已加载 {len(software_list)} 个软件")
        self.clear_selection_detail()

    def scan_software_directory(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT path FROM software")
        existing_paths = {row[0] for row in cursor.fetchall()}

        entries = os.listdir(self.software_dir)
        for entry in entries:
            full_entry_path = os.path.join(self.software_dir, entry)
            rel_path = entry
            if rel_path in existing_paths:
                continue
            if os.path.isfile(full_entry_path):
                name = os.path.splitext(entry)[0]
                cursor.execute("""
                    INSERT INTO software (name, filename, path, description)
                    VALUES (?, ?, ?, ?)
                """, (name, entry, rel_path, ""))
            elif os.path.isdir(full_entry_path):
                name = entry
                cursor.execute("""
                    INSERT INTO software (name, filename, path, description)
                    VALUES (?, ?, ?, ?)
                """, (name, "", rel_path, ""))
        conn.commit()
        conn.close()

    def get_software_list(self, search_text="", active_tags=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT id, name, filename, path, description FROM software"
        params = []

        if search_text:
            query += " WHERE (LOWER(name) LIKE ? OR LOWER(description) LIKE ?)"
            params.extend([f"%{search_text}%", f"%{search_text}%"])

        if active_tags:
            tag_ids = []
            for tag in active_tags:
                cursor.execute("SELECT id FROM tags WHERE name=?", (tag,))
                result = cursor.fetchone()
                if result:
                    tag_ids.append(result[0])

            if tag_ids:
                placeholders = ",".join("?" * len(tag_ids))
                if "WHERE" in query:
                    query += f" AND id IN (SELECT software_id FROM software_tags WHERE tag_id IN ({placeholders}))"
                else:
                    query += f" WHERE id IN (SELECT software_id FROM software_tags WHERE tag_id IN ({placeholders}))"
                params.extend(tag_ids)

        cursor.execute(query, params)
        result = cursor.fetchall()
        conn.close()
        return result

    def get_all_tags(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM tags ORDER BY name")
        tags = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tags

    def get_tags_for_software(self, software_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.name
            FROM tags t
            JOIN software_tags st ON t.id = st.tag_id
            WHERE st.software_id=?
        """, (software_id,))
        tags = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tags

    def on_software_select(self, event):
        selected_items = self.tree.selection()
        if not selected_items:
            self.clear_selection_detail()
            return

        item = selected_items[0]
        if not item.startswith("sw_"):
            self.clear_selection_detail()
            return

        software_id = int(item[3:])
        self.selected_software_id = software_id

        self.run_btn.config(state=tk.NORMAL)
        self.edit_btn.config(state=tk.NORMAL)
        self.manage_tags_btn.config(state=tk.NORMAL)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name, path, description FROM software WHERE id=?", (software_id,))
        result = cursor.fetchone()
        conn.close()

        if result:
            name, path, description = result
            tags = self.get_tags_for_software(software_id)

            self.detail_vars["名称"].set(name)
            self.detail_vars["路径"].set(path)
            self.detail_vars["描述"].set(description)
            self.detail_vars["标签"].set(", ".join(tags))

    def clear_selection_detail(self):
        self.selected_software_id = None
        for var in self.detail_vars.values():
            var.set("")
        self.run_btn.config(state=tk.DISABLED)
        self.edit_btn.config(state=tk.DISABLED)
        self.manage_tags_btn.config(state=tk.DISABLED)

    def on_software_double_click(self, event):
        self.run_selected_software()

    def run_selected_software(self):
        if not self.selected_software_id:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT path FROM software WHERE id=?", (self.selected_software_id,))
        result = cursor.fetchone()
        conn.close()

        if result:
            path = result[0]
            full_path = os.path.join(self.software_dir, path)
            try:
                os.startfile(full_path)

                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE software
                    SET use_count = use_count + 1, last_used = ?
                    WHERE id = ?
                """, (datetime.now().isoformat(), self.selected_software_id))
                conn.commit()
                conn.close()

                self.update_status(f"已启动: {os.path.basename(full_path)}")
            except Exception as e:
                messagebox.showerror("错误", f"无法启动:\n{str(e)}")

    def edit_software(self):
        if not self.selected_software_id:
            return

        edit_win = tk.Toplevel(self.root)
        edit_win.title("编辑软件信息")
        edit_win.geometry("400x320")
        edit_win.transient(self.root)
        edit_win.grab_set()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name, description FROM software WHERE id=?", (self.selected_software_id,))
        res = cursor.fetchone()
        conn.close()
        if res is None:
            messagebox.showerror("错误", "软件信息读取失败")
            edit_win.destroy()
            return

        name, description = res

        ttk.Label(edit_win, text="软件名称:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        name_var = tk.StringVar(value=name)
        name_entry = ttk.Entry(edit_win, textvariable=name_var, width=40)
        name_entry.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(edit_win, text="功能描述:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        desc_text = tk.Text(edit_win, height=10)
        desc_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        desc_text.insert("1.0", description)

        btn_frame = ttk.Frame(edit_win)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        def save_changes():
            new_name = name_var.get().strip()
            new_desc = desc_text.get("1.0", "end-1c").strip()
            if not new_name:
                messagebox.showwarning("警告", "软件名称不能为空")
                return
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE software
                SET name=?, description=?
                WHERE id=?
            """, (new_name, new_desc, self.selected_software_id))
            conn.commit()
            conn.close()

            self.refresh_software_list()
            edit_win.destroy()
            self.update_status("软件信息已更新")

        ttk.Button(btn_frame, text="保存", command=save_changes).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=edit_win.destroy).pack(side=tk.RIGHT)

    def add_software(self):
        file_path = filedialog.askopenfilename(
            title="选择软件文件",
            filetypes=[("可执行文件", "*.exe"), ("安装包", "*.msi"), ("批处理文件", "*.bat"), ("所有文件", "*.*")]
        )
        if not file_path:
            return

        dest_path = None

        try:
            abs_software_dir = os.path.abspath(self.software_dir)
            abs_file_path = os.path.abspath(file_path)

            if not abs_file_path.startswith(abs_software_dir):
                dest_path = os.path.join(self.software_dir, os.path.basename(file_path))
                counter = 1
                base, ext = os.path.splitext(dest_path)
                while os.path.exists(dest_path):
                    dest_path = f"{base}_{counter}{ext}"
                    counter += 1
                shutil.copy2(file_path, dest_path)
            else:
                dest_path = file_path
        except Exception as e:
            messagebox.showerror("错误", f"无法复制文件:\n{str(e)}")
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        rel_path = os.path.relpath(dest_path, self.software_dir)
        name = os.path.splitext(os.path.basename(dest_path))[0]

        try:
            cursor.execute("""
                INSERT INTO software (name, filename, path, description)
                VALUES (?, ?, ?, ?)
            """, (name, os.path.basename(dest_path), rel_path, ""))
            conn.commit()
            self.update_status(f"已添加软件: {os.path.basename(dest_path)}")
        except sqlite3.IntegrityError:
            messagebox.showwarning("警告", "该软件已存在")
        finally:
            conn.close()

        self.refresh_software_list()

    def clear_tag_filter(self):
        for var in self.tag_vars.values():
            var.set(False)
        self.refresh_software_list()

    def manage_tags_for_selected(self):
        if not self.selected_software_id:
            return

        self.notebook.select(1)

        software_prefix = f"[{self.selected_software_id}]"
        for i in range(self.tags_software_list.size()):
            text = self.tags_software_list.get(i)
            if text.startswith(software_prefix):
                self.tags_software_list.selection_clear(0, tk.END)
                self.tags_software_list.selection_set(i)
                self.tags_software_list.see(i)
                self.on_tags_software_select()
                break

    def refresh_tags_ui(self):
        self.tags_software_list.delete(0, tk.END)
        software_list = self.get_software_list()
        for sw in software_list:
            tags = self.get_tags_for_software(sw[0])
            self.tags_software_list.insert(tk.END, f"[{sw[0]}] {sw[1]} - {', '.join(tags)}")

        self.delete_tag_combo["values"] = self.get_all_tags()
        if self.delete_tag_combo["values"]:
            self.delete_tag_combo.current(0)

        self.update_tags_buttons()

    def on_tags_software_select(self, event=None):
        selected_indices = self.tags_software_list.curselection()
        if not selected_indices:
            self.current_software_id = None
            self.current_tags_var.set("无")
            self.selected_tags = set()
            self.update_tags_buttons()
            return

        index = selected_indices[0]
        item = self.tags_software_list.get(index)
        try:
            software_id = int(item.split("]")[0][1:])
        except Exception:
            software_id = None

        self.current_software_id = software_id

        if software_id is not None:
            tags = self.get_tags_for_software(software_id)
            self.selected_tags = set(tags)
            self.current_tags_var.set(", ".join(tags) if tags else "无")
        else:
            self.selected_tags = set()
            self.current_tags_var.set("无")

        self.update_tags_buttons()

    def update_tags_buttons(self):
        for widget in self.tags_buttons_frame.winfo_children():
            widget.destroy()

        for tag in self.get_all_tags():
            is_selected = tag in self.selected_tags
            style = ttk.Style()
            style_name = f"{tag}.TButton"
            style.configure(style_name, relief="sunken" if is_selected else "raised")

            btn = ttk.Button(
                self.tags_buttons_frame,
                text=tag,
                style=style_name,
                command=lambda t=tag: self.toggle_tag_selection(t)
            )
            btn.pack(side=tk.LEFT, padx=3, pady=3)

    def toggle_tag_selection(self, tag):
        if tag in self.selected_tags:
            self.selected_tags.remove(tag)
        else:
            self.selected_tags.add(tag)

        self.current_tags_var.set(", ".join(sorted(self.selected_tags)) if self.selected_tags else "无")
        self.update_tags_buttons()

    def add_new_tag(self):
        new_tag = self.new_tag_var.get().strip()
        if not new_tag:
            messagebox.showwarning("警告", "标签名称不能为空")
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("INSERT INTO tags (name) VALUES (?)", (new_tag,))
            conn.commit()
            self.new_tag_var.set("")
            self.all_tags = self.get_all_tags()
            self.refresh_tags_ui()

            if new_tag not in self.tag_vars:
                var = tk.BooleanVar(value=False)
                cb = ttk.Checkbutton(self.tag_filter_frame, text=new_tag, variable=var, command=self.refresh_software_list)
                cb.pack(side=tk.LEFT, padx=4, pady=5)
                self.tag_vars[new_tag] = var

            self.update_status(f"已添加标签: {new_tag}")
        except sqlite3.IntegrityError:
            messagebox.showwarning("警告", f"标签 '{new_tag}' 已存在")
        finally:
            conn.close()

    def delete_tag(self):
        tag = self.delete_tag_var.get()
        if not tag:
            return

        if not messagebox.askyesno("确认删除", f"确定要删除标签 '{tag}' 吗？\n此操作无法撤销。"):
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM tags WHERE name=?", (tag,))
        res = cursor.fetchone()
        if res is None:
            messagebox.showerror("错误", "标签不存在")
            conn.close()
            return

        tag_id = res[0]

        cursor.execute("DELETE FROM software_tags WHERE tag_id=?", (tag_id,))
        cursor.execute("DELETE FROM tags WHERE id=?", (tag_id,))

        conn.commit()
        conn.close()

        self.all_tags = self.get_all_tags()
        self.refresh_tags_ui()

        if tag in self.tag_vars:
            var = self.tag_vars[tag]
            var.set(False)
            for child in self.tag_filter_frame.winfo_children():
                if isinstance(child, ttk.Checkbutton) and child.cget("text") == tag:
                    child.destroy()
                    break
            del self.tag_vars[tag]

        self.refresh_software_list()
        self.update_status(f"已删除标签: {tag}")

    def save_tags_changes(self):
        if not self.current_software_id:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM software_tags WHERE software_id=?", (self.current_software_id,))
            for tag in self.selected_tags:
                cursor.execute("SELECT id FROM tags WHERE name=?", (tag,))
                res = cursor.fetchone()
                if res:
                    tag_id = res[0]
                    cursor.execute("INSERT INTO software_tags (software_id, tag_id) VALUES (?, ?)",
                                  (self.current_software_id, tag_id))
            conn.commit()
            self.refresh_tags_ui()
            self.refresh_software_list()
            self.update_status("已更新标签")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败:\n{str(e)}")
        finally:
            conn.close()

    def update_status(self, message):
        self.status_var.set(f"状态: {message} | 程序路径: {self.usb_drive}")


if __name__ == "__main__":
    root = tk.Tk()
    app = SoftwareManager(root)
    root.mainloop()