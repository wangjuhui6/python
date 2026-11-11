# -*- coding: utf-8 -*-
"""把总表每一行的数据，写入对应人员文件夹里的同名表格。

总表每一行是一个人。默认用 A 列的文字，到目标文件夹下找同名子文件夹，
再打开其中同名的 xlsx（例如「姓名1/姓名1.xlsx」）。

映射可以加很多条：总表的某一列 → 该人员表格的「工作表 + 单元格」。
例如 B 列写入「基本情况」的 B3，C 列写入「第二个」的 B1。

运行：
    python fill_excel.py
依赖：
    python -m pip install openpyxl
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import openpyxl
    from openpyxl.cell.cell import MergedCell
    from openpyxl.utils import column_index_from_string, coordinate_to_tuple, get_column_letter
except ModuleNotFoundError:  # 在 main 里提示，避免双击后只闪一下控制台
    openpyxl = None
    MergedCell = ()
    column_index_from_string = None
    coordinate_to_tuple = None
    get_column_letter = None


EXAMPLE_SOURCE = Path(r"C:\Users\13934\Downloads\姓名-年龄-岁数.xlsx")
EXAMPLE_FOLDER = Path(r"C:\Users\13934\Downloads\新建文件夹")
CONFIG_NAME = "映射配置.json"
FONT = ("Microsoft YaHei UI", 10)
FONT_SM = ("Microsoft YaHei UI", 9)
INVALID_NAME_CHARS = set('\\/:*?"<>|')


@dataclass
class Mapping:
    column: str
    sheet: str
    cell: str


@dataclass
class SheetData:
    sheet_names: list[str]
    sheet: str
    columns: list[str]
    max_row: int
    values: dict[tuple[int, str], object]

    def get(self, row: int, column: str):
        return self.values.get((row, column))


def require_openpyxl() -> None:
    if openpyxl is None:
        raise ModuleNotFoundError("openpyxl")


def display(value) -> str:
    if value is None or value == "":
        return "空"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def as_name(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def safe_person_name(name: str) -> bool:
    if not name or name in {".", ".."} or name.startswith("~$"):
        return False
    return not any(ch in name for ch in INVALID_NAME_CHARS)


def norm_column(text: str) -> str:
    require_openpyxl()
    raw = text.strip().upper().replace("列", "").replace(" ", "")
    index = column_index_from_string(raw)
    return get_column_letter(index)


def norm_cell(text: str) -> str:
    require_openpyxl()
    raw = text.strip().upper().replace("$", "").replace(" ", "").replace("，", "")
    if "!" in raw:
        raw = raw.split("!")[-1]
    row, col = coordinate_to_tuple(raw)
    if row < 1:
        raise ValueError(raw)
    return f"{get_column_letter(col)}{row}"


def load_sheet(path: Path, sheet_name: str | None = None) -> SheetData:
    """读取总表里实际有内容的区域。公式优先用 Excel 缓存的计算结果。"""
    require_openpyxl()
    workbook = openpyxl.load_workbook(path, data_only=False)
    try:
        names = list(workbook.sheetnames)
        if sheet_name:
            if sheet_name not in names:
                raise ValueError(f"总表里没有工作表「{sheet_name}」")
            worksheet = workbook[sheet_name]
        else:
            worksheet = workbook.active
        max_row = min(worksheet.max_row or 1, 10000)
        max_col = min(worksheet.max_column or 1, 200)
        values: dict[tuple[int, str], object] = {}
        formulas: list[tuple[int, int, str, str]] = []
        for row in worksheet.iter_rows(min_row=1, max_row=max_row, max_col=max_col):
            for cell in row:
                if cell.value is None or cell.value == "":
                    continue
                letter = get_column_letter(cell.column)
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    formulas.append((cell.row, cell.column, letter, cell.value))
                else:
                    values[(cell.row, letter)] = cell.value
        chosen = worksheet.title
    finally:
        workbook.close()

    if formulas:
        cached = openpyxl.load_workbook(path, data_only=True)
        try:
            worksheet = cached[chosen]
            for row, col, letter, formula in formulas:
                cached_value = worksheet.cell(row, col).value
                # 没有缓存结果时保留公式文本，后面会拦住，避免把空值写进人员表
                values[(row, letter)] = formula if cached_value is None else cached_value
        finally:
            cached.close()

    last_row = 1
    last_col = 1
    for (row, letter), value in values.items():
        if value is None or str(value).strip() == "":
            continue
        last_row = max(last_row, row)
        last_col = max(last_col, column_index_from_string(letter))
    columns = [get_column_letter(i) for i in range(1, last_col + 1)]
    trimmed = {
        key: value
        for key, value in values.items()
        if key[0] <= last_row and column_index_from_string(key[1]) <= last_col
    }
    return SheetData(names, chosen, columns, last_row, trimmed)


def iter_workbooks(folder: Path):
    if not folder.is_dir():
        return
    for child in sorted(folder.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        files = []
        try:
            children = list(child.iterdir())
        except OSError:
            continue
        for item in children:
            if not item.is_file():
                continue
            if item.name.startswith("~$") or item.name.startswith(".~"):
                continue
            if item.suffix.lower() not in {".xlsx", ".xlsm"}:
                continue
            if item.stem.endswith(".bak"):
                continue
            files.append(item)
        yield child, files


def find_target_file(folder: Path, name: str) -> tuple[Path | None, str]:
    person_dir = None
    direct = folder / name
    if direct.is_dir():
        person_dir = direct
    else:
        for child, _files in iter_workbooks(folder):
            if child.name.strip() == name:
                person_dir = child
                break
    if person_dir is None:
        return None, "没有同名文件夹"

    files = []
    for child, found in iter_workbooks(folder):
        if child == person_dir:
            files = found
            break
    preferred = [item for item in files if item.stem == name or item.stem == person_dir.name]
    if preferred:
        preferred.sort(key=lambda item: item.suffix.lower() != ".xlsx")
        return preferred[0], ""
    if len(files) == 1:
        return files[0], ""
    if not files:
        return None, "文件夹里没有 xlsx 表格"
    return None, "有多张表格，但没有与文件夹同名的文件"


def discover_folder(folder: Path) -> tuple[list[str], list[str]]:
    people: list[str] = []
    sheets: list[str] = []
    for child, files in iter_workbooks(folder):
        people.append(child.name)
        if sheets or not files:
            continue
        workbook = openpyxl.load_workbook(files[0], read_only=True)
        try:
            sheets = list(workbook.sheetnames)
        finally:
            workbook.close()
    return people, sheets


def locate_cell(worksheet, coord: str):
    """返回真正可写入的单元格。合并区域里只能写左上角。"""
    for merged in worksheet.merged_cells.ranges:
        if coord in merged:
            anchor_coord = f"{get_column_letter(merged.min_col)}{merged.min_row}"
            anchor = worksheet[anchor_coord]
            note = ""
            if anchor_coord != coord:
                note = f"{coord} 在合并区域 {merged} 内，改为写入 {anchor_coord}"
            return anchor, anchor.value, note
    cell = worksheet[coord]
    if isinstance(cell, MergedCell):
        raise ValueError(f"{coord} 是合并单元格，无法写入")
    return cell, cell.value, ""


def run_fill(
    source: Path,
    folder: Path,
    source_sheet: str | None,
    name_col: str,
    start_row: int,
    mappings: list[Mapping],
    write: bool,
    backup: bool,
) -> tuple[list[str], dict]:
    require_openpyxl()
    lines: list[str] = []
    stats = {"people": 0, "ok": 0, "errors": 0, "warnings": 0}

    def add(text: str = "") -> None:
        lines.append(text)

    if not source.is_file():
        add(f"找不到总表：{source}")
        stats["errors"] += 1
        return lines, stats
    if not folder.is_dir():
        add(f"找不到人员文件夹：{folder}")
        stats["errors"] += 1
        return lines, stats
    if start_row < 1:
        add("起始行必须大于 0。")
        stats["errors"] += 1
        return lines, stats
    if not mappings:
        add("还没有映射。请先指定每一列写到哪个单元格。")
        stats["errors"] += 1
        return lines, stats

    try:
        name_col = norm_column(name_col)
        clean_mappings = [
            Mapping(norm_column(item.column), item.sheet.strip(), norm_cell(item.cell))
            for item in mappings
        ]
    except Exception as exc:  # 列号或单元格地址不合法
        add(f"映射格式不对：{exc}")
        stats["errors"] += 1
        return lines, stats

    try:
        data = load_sheet(source, source_sheet)
    except Exception as exc:
        add(f"读取总表失败：{exc}")
        stats["errors"] += 1
        return lines, stats

    add(f"总表：{source}")
    add(f"工作表：{data.sheet}    人员文件夹：{folder}")
    add(f"用 {name_col} 列匹配文件夹，从第 {start_row} 行开始。")
    add("映射：")
    for item in clean_mappings:
        add(f"  {item.column} 列  →  {item.sheet}!{item.cell}")
    add("")

    if start_row > data.max_row:
        add("起始行之后没有数据。")
        stats["errors"] += 1
        return lines, stats

    for row in range(start_row, data.max_row + 1):
        name = as_name(data.get(row, name_col))
        has_other = any(
            data.get(row, item.column) not in (None, "")
            for item in clean_mappings
        )
        if not name:
            if has_other:
                add(f"第 {row} 行没有{name_col}列姓名，已跳过。")
                stats["warnings"] += 1
            continue
        stats["people"] += 1
        if not safe_person_name(name):
            add(f"第 {row} 行「{name}」不能当作文件夹名，已跳过。")
            stats["errors"] += 1
            continue

        target, reason = find_target_file(folder, name)
        if target is None:
            add(f"第 {row} 行「{name}」{reason}，已跳过。")
            stats["errors"] += 1
            continue
        try:
            if target.resolve() == source.resolve():
                add(f"第 {row} 行「{name}」的目标就是总表本身，已跳过。")
                stats["errors"] += 1
                continue
        except OSError:
            pass

        add(f"第 {row} 行  {name}")
        add(f"  文件：{target}")
        problems: list[str] = []
        planned: list[tuple[str, str, str, object]] = []
        for item in clean_mappings:
            value = data.get(row, item.column)
            if isinstance(value, str) and value.startswith("="):
                problems.append(
                    f"{item.column} 列是公式 {value}，总表里没有计算结果。请先用 Excel 打开总表并保存。"
                )
                continue
            planned.append((item.column, item.sheet, item.cell, value))

        workbook = None
        try:
            workbook = openpyxl.load_workbook(
                target, keep_vba=target.suffix.lower() == ".xlsm"
            )
            actions = []
            for column, sheet, cell, value in planned:
                if sheet not in workbook.sheetnames:
                    problems.append(f"没有工作表「{sheet}」，{column} 列无法写入 {sheet}!{cell}")
                    continue
                try:
                    _cell, old, note = locate_cell(workbook[sheet], cell)
                except Exception as exc:
                    problems.append(f"{sheet}!{cell} 无法写入：{exc}")
                    continue
                actions.append((column, sheet, _cell, value, old, note))

            if problems:
                for problem in problems:
                    add(f"  未写入：{problem}")
                add("  这个文件没有保存。")
                stats["errors"] += 1
                continue

            for column, sheet, cell, value, old, note in actions:
                extra = f"。{note}" if note else ""
                add(
                    f"  {column} 列「{display(value)}」→ {sheet}!{cell.coordinate}"
                    f"（原来是{display(old)}）{extra}"
                )
                if write:
                    cell.value = value

            if write:
                backup_path = target.with_name(f"{target.stem}.bak{target.suffix}")
                if backup:
                    if backup_path.exists():
                        add(f"  已有备份，保留不动：{backup_path.name}")
                    else:
                        shutil.copy2(target, backup_path)
                        add(f"  已备份：{backup_path.name}")
                temporary = target.with_name(f".~{target.name}.tmp")
                try:
                    workbook.save(temporary)
                    os.replace(temporary, target)
                finally:
                    if temporary.exists():
                        temporary.unlink()
                add("  已保存。")
            else:
                add("  预览通过，未修改文件。")
            stats["ok"] += 1
        except PermissionError:
            add("  保存失败：文件可能正被 Excel 打开，请先关闭后再写入。")
            stats["errors"] += 1
        except Exception as exc:
            add(f"  处理失败：{exc}")
            stats["errors"] += 1
        finally:
            if workbook is not None:
                workbook.close()
        add("")

    if write:
        add(f"写入结束：成功 {stats['ok']} 个，有问题 {stats['errors']} 个。")
    else:
        add(
            f"预览结束：可以通过 {stats['ok']} 个，有问题 {stats['errors']} 个。尚未修改任何文件。"
        )
    if stats["people"] == 0:
        add(f"没有匹配到人员。请确认{name_col}列和起始行。")
    return lines, stats


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("批量写入人员表格")
        self.minsize(880, 680)
        self.configure(bg="#f4f6f8")
        self._ready = False
        self._loading = False
        self.running = False
        self.cache: SheetData | None = None
        self.mappings: list[Mapping] = []
        self.log_queue: queue.Queue = queue.Queue()

        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=FONT)
        style.configure("Treeview", rowheight=26, font=FONT_SM)
        style.configure("Treeview.Heading", font=FONT)
        style.configure("TButton", padding=(10, 4))
        style.configure("Primary.TButton", padding=(12, 4), font=("Microsoft YaHei UI", 10, "bold"))

        self.source_var = tk.StringVar()
        self.folder_var = tk.StringVar()
        self.sheet_var = tk.StringVar()
        self.name_var = tk.StringVar(value="A")
        self.start_var = tk.IntVar(value=1)
        self.header_var = tk.BooleanVar(value=False)
        self.backup_var = tk.BooleanVar(value=True)
        self.map_col = tk.StringVar(value="B")
        self.map_sheet = tk.StringVar()
        self.map_cell = tk.StringVar()
        self.col_hint = tk.StringVar()
        self.folder_hint = tk.StringVar(value="选择人员文件夹后，这里会列出子文件夹和工作表。")

        self._build()
        self._place_window()
        self._ready = True
        self.write_log(self._intro())
        self._load_examples()
        self.after(120, self._poll)

    def _intro(self) -> str:
        return (
            "每一行是一个人。程序用「姓名列」的文字去找同名文件夹，再打开里面同名的表格。\n"
            "然后按你添加的映射，把这一行某一列的值写进指定工作表的单元格。映射可以加很多条。\n"
            "建议先预览。写入时默认在原文件旁另存一份，例如「姓名1.bak.xlsx」，已有备份不会覆盖。\n"
        )

    def _place_window(self) -> None:
        width, height = 980, 760
        self.update_idletasks()
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        form = ttk.LabelFrame(outer, text="文件", padding=10)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="总表").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(form, textvariable=self.source_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(form, text="选择", command=self.choose_source).grid(row=0, column=2)
        ttk.Label(form, text="工作表").grid(row=0, column=3, padx=(12, 4))
        self.source_sheet = ttk.Combobox(form, textvariable=self.sheet_var, width=16, state="readonly")
        self.source_sheet.grid(row=0, column=4)
        self.source_sheet.bind("<<ComboboxSelected>>", self._on_source_sheet)

        ttk.Label(form, text="人员文件夹").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(form, textvariable=self.folder_var).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(form, text="选择", command=self.choose_folder).grid(row=1, column=2)
        ttk.Label(form, textvariable=self.folder_hint, foreground="#52606d").grid(
            row=2, column=1, columnspan=4, sticky="w", padx=6
        )

        option = ttk.Frame(form)
        option.grid(row=3, column=0, columnspan=5, sticky="w", pady=(8, 0))
        ttk.Label(option, text="姓名列").pack(side="left")
        self.name_combo = ttk.Combobox(option, textvariable=self.name_var, width=6, values=["A"])
        self.name_combo.pack(side="left", padx=(6, 16))
        self.name_combo.bind("<<ComboboxSelected>>", lambda _event: self.render_preview())
        ttk.Label(option, text="从第").pack(side="left")
        spin = ttk.Spinbox(option, from_=1, to=100000, textvariable=self.start_var, width=6)
        spin.pack(side="left", padx=4)
        ttk.Label(option, text="行开始").pack(side="left", padx=(0, 16))
        ttk.Checkbutton(
            option,
            text="第 1 行是表头，不参与匹配",
            variable=self.header_var,
            command=self._on_header,
        ).pack(side="left")

        preview_box = ttk.LabelFrame(outer, text="总表预览", padding=8)
        preview_box.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        preview_box.columnconfigure(0, weight=1)
        preview_box.rowconfigure(0, weight=1)
        self.preview_frame = ttk.Frame(preview_box)
        self.preview_frame.grid(row=0, column=0, sticky="nsew")
        self.preview_frame.columnconfigure(0, weight=1)
        self.preview_frame.rowconfigure(0, weight=1)
        self.preview: ttk.Treeview | None = None
        self._make_preview(["行"])

        mapping_box = ttk.LabelFrame(outer, text="列映射（可以添加很多条）", padding=8)
        mapping_box.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        mapping_box.columnconfigure(0, weight=1)

        editor = ttk.Frame(mapping_box)
        editor.grid(row=0, column=0, sticky="ew")
        ttk.Label(editor, text="源列").pack(side="left")
        self.map_col_combo = ttk.Combobox(editor, textvariable=self.map_col, width=6, values=["A", "B", "C"])
        self.map_col_combo.pack(side="left", padx=(4, 10))
        self.map_col_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_column_hint())
        ttk.Label(editor, text="目标工作表").pack(side="left")
        self.map_sheet_combo = ttk.Combobox(editor, textvariable=self.map_sheet, width=18)
        self.map_sheet_combo.pack(side="left", padx=(4, 10))
        ttk.Label(editor, text="单元格").pack(side="left")
        cell_entry = ttk.Entry(editor, textvariable=self.map_cell, width=10)
        cell_entry.pack(side="left", padx=(4, 10))
        cell_entry.bind("<Return>", lambda _event: self.add_mapping())
        ttk.Button(editor, text="添加", command=self.add_mapping).pack(side="left", padx=2)
        ttk.Button(editor, text="更新选中", command=self.update_mapping).pack(side="left", padx=2)
        ttk.Button(editor, text="删除选中", command=self.delete_mapping).pack(side="left", padx=2)

        ttk.Label(mapping_box, textvariable=self.col_hint, foreground="#52606d").grid(
            row=1, column=0, sticky="w", pady=(6, 4)
        )

        columns = ("column", "sheet", "cell")
        self.map_tree = ttk.Treeview(
            mapping_box, columns=columns, show="headings", height=5, selectmode="extended"
        )
        self.map_tree.heading("column", text="总表列")
        self.map_tree.heading("sheet", text="目标工作表")
        self.map_tree.heading("cell", text="目标单元格")
        self.map_tree.column("column", width=120, anchor="center")
        self.map_tree.column("sheet", width=280, anchor="w")
        self.map_tree.column("cell", width=160, anchor="center")
        self.map_tree.grid(row=2, column=0, sticky="ew")
        self.map_tree.bind("<<TreeviewSelect>>", self._on_mapping_select)
        self.map_tree.bind("<Delete>", lambda _event: self.delete_mapping())

        actions = ttk.Frame(outer)
        actions.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.preview_button = ttk.Button(actions, text="预览", command=self.preview)
        self.preview_button.pack(side="left")
        self.write_button = ttk.Button(
            actions, text="开始写入", style="Primary.TButton", command=self.write_files
        )
        self.write_button.pack(side="left", padx=8)
        ttk.Checkbutton(actions, text="写入前另存一份 bak 表格", variable=self.backup_var).pack(
            side="left", padx=(4, 16)
        )
        ttk.Button(actions, text="保存配置", command=self.save_config).pack(side="right")
        ttk.Button(actions, text="载入配置", command=self.load_config).pack(side="right", padx=(0, 8))

        log_box = ttk.LabelFrame(outer, text="日志", padding=8)
        log_box.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        log_box.columnconfigure(0, weight=1)
        log_box.rowconfigure(0, weight=1)
        self.log = tk.Text(
            log_box,
            height=10,
            wrap="word",
            font=FONT_SM,
            relief="flat",
            bg="#ffffff",
            fg="#1f2933",
            padx=8,
            pady=6,
        )
        scroll = ttk.Scrollbar(log_box, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set, state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        self.start_var.trace_add("write", lambda *_args: self.render_preview())

    def _make_preview(self, headers: list[str]) -> None:
        for child in self.preview_frame.winfo_children():
            child.destroy()
        self.preview = ttk.Treeview(
            self.preview_frame, columns=headers, show="headings", height=6
        )
        for header in headers:
            self.preview.heading(header, text=header)
            width = 54 if header == "行" else 140
            self.preview.column(header, width=width, anchor="center" if header == "行" else "w")
        y_scroll = ttk.Scrollbar(self.preview_frame, command=self.preview.yview)
        x_scroll = ttk.Scrollbar(self.preview_frame, orient="horizontal", command=self.preview.xview)
        self.preview.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.preview.tag_configure("skip", background="#eef2f5")
        self.preview.tag_configure("data", background="#ffffff")
        self.preview.tag_configure("data2", background="#f3f8f4")
        self.preview.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

    def write_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text if text.endswith("\n") else text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _load_examples(self) -> None:
        if EXAMPLE_SOURCE.is_file():
            self.source_var.set(str(EXAMPLE_SOURCE))
            self.reload_source(popup=False)
        if EXAMPLE_FOLDER.is_dir():
            self.folder_var.set(str(EXAMPLE_FOLDER))
            self.reload_folder(popup=False)

    def choose_source(self) -> None:
        initial = self.source_var.get() or str(EXAMPLE_SOURCE.parent)
        path = filedialog.askopenfilename(
            title="选择总表",
            initialdir=str(Path(initial).parent if initial else Path.home()),
            filetypes=[("Excel 表格", "*.xlsx *.xlsm"), ("所有文件", "*.*")],
        )
        if not path:
            return
        self.source_var.set(path)
        self.reload_source(popup=True)

    def choose_folder(self) -> None:
        initial = self.folder_var.get() or str(EXAMPLE_FOLDER)
        path = filedialog.askdirectory(title="选择人员文件夹", initialdir=initial)
        if not path:
            return
        self.folder_var.set(path)
        self.reload_folder(popup=True)

    def _on_source_sheet(self, _event=None) -> None:
        if self._loading:
            return
        self.reload_source(popup=True)

    def _on_header(self) -> None:
        if self.header_var.get() and self._start_row() < 2:
            self.start_var.set(2)
        elif not self.header_var.get() and self._start_row() == 2:
            self.start_var.set(1)
        self.render_preview()

    def _start_row(self) -> int:
        try:
            return int(self.start_var.get())
        except (tk.TclError, ValueError):
            return 1

    def reload_source(self, popup: bool) -> None:
        path = Path(self.source_var.get().strip())
        if not path.is_file():
            self.cache = None
            message = f"找不到总表：{path}"
            if popup:
                messagebox.showerror("总表", message)
            else:
                self.write_log(message)
            return
        try:
            sheet = self.sheet_var.get().strip() or None
            data = load_sheet(path, sheet)
        except Exception as exc:
            self.cache = None
            message = f"读取总表失败：{exc}"
            if popup:
                messagebox.showerror("总表", message)
            else:
                self.write_log(message)
            return
        self.cache = data
        self._loading = True
        try:
            self.source_sheet["values"] = data.sheet_names
            self.sheet_var.set(data.sheet)
            letters = data.columns or ["A"]
            self.name_combo["values"] = letters
            self.map_col_combo["values"] = letters
            if self.name_var.get() not in letters:
                self.name_var.set(letters[0])
            if self.map_col.get() not in letters:
                self.map_col.set(letters[1] if len(letters) > 1 else letters[0])
        finally:
            self._loading = False
        self.render_preview()
        self.update_column_hint()

    def reload_folder(self, popup: bool) -> None:
        folder = Path(self.folder_var.get().strip())
        if not folder.is_dir():
            self.folder_hint.set("文件夹不存在。")
            if popup:
                messagebox.showerror("人员文件夹", f"找不到文件夹：{folder}")
            return
        try:
            people, sheets = discover_folder(folder)
        except Exception as exc:
            self.folder_hint.set(f"读取文件夹失败：{exc}")
            if popup:
                messagebox.showerror("人员文件夹", str(exc))
            return
        shown = "、".join(people[:10])
        if len(people) > 10:
            shown += "…"
        sheet_text = "、".join(sheets) if sheets else "没有读到工作表"
        if people:
            self.folder_hint.set(f"子文件夹 {len(people)} 个：{shown}。示例表格的工作表：{sheet_text}")
        else:
            self.folder_hint.set("这个文件夹下没有子文件夹。")
        self.map_sheet_combo["values"] = sheets
        if sheets and not self.map_sheet.get().strip():
            self.map_sheet.set(sheets[0])

    def render_preview(self) -> None:
        if not self._ready:
            return
        data = self.cache
        if data is None or self.preview is None:
            return
        headers = ["行"] + data.columns
        if list(self.preview["columns"]) != headers:
            self._make_preview(headers)
        assert self.preview is not None
        self.preview.delete(*self.preview.get_children())
        start = self._start_row()
        visible = min(data.max_row, 12)
        data_index = 0
        for row in range(1, visible + 1):
            values = [row] + [display(data.get(row, column)) if data.get(row, column) not in (None, "") else "" for column in data.columns]
            if row < start:
                tag = "skip"
            else:
                tag = "data" if data_index % 2 == 0 else "data2"
                data_index += 1
            self.preview.insert("", "end", values=values, tags=(tag,))
        if data.max_row > visible:
            self.preview.insert("", "end", values=[f"… 共 {data.max_row} 行"] + [""] * len(data.columns))

    def update_column_hint(self) -> None:
        data = self.cache
        letter = self.map_col.get().strip().upper() or "B"
        if data is None:
            self.col_hint.set("先选择总表，这里会显示这一列的内容。")
            return
        samples = []
        for row in range(1, min(data.max_row, 3) + 1):
            samples.append(f"第{row}行 {display(data.get(row, letter))}")
        self.col_hint.set(f"{letter} 列示例：" + "，".join(samples) + "。灰色行不会参与匹配。")

    def _read_mapping_form(self) -> Mapping:
        column = norm_column(self.map_col.get())
        sheet = self.map_sheet.get().strip()
        cell = norm_cell(self.map_cell.get())
        if not sheet:
            raise ValueError("请填写目标工作表")
        return Mapping(column, sheet, cell)

    def add_mapping(self) -> None:
        try:
            mapping = self._read_mapping_form()
        except Exception as exc:
            messagebox.showerror("映射", f"这一条映射不对：{exc}")
            return
        if any(item == mapping for item in self.mappings):
            messagebox.showinfo("映射", "同样的映射已经在列表里。")
            return
        self.mappings.append(mapping)
        self._refresh_mapping_tree(select=len(self.mappings) - 1)

    def update_mapping(self) -> None:
        selected = self.map_tree.selection()
        if len(selected) != 1:
            messagebox.showinfo("映射", "请先在列表里选中一条映射。")
            return
        try:
            mapping = self._read_mapping_form()
        except Exception as exc:
            messagebox.showerror("映射", f"这一条映射不对：{exc}")
            return
        index = self.map_tree.index(selected[0])
        self.mappings[index] = mapping
        self._refresh_mapping_tree(select=index)

    def delete_mapping(self) -> None:
        selected = list(self.map_tree.selection())
        if not selected:
            return
        indexes = sorted((self.map_tree.index(item) for item in selected), reverse=True)
        for index in indexes:
            del self.mappings[index]
        self._refresh_mapping_tree()

    def _on_mapping_select(self, _event=None) -> None:
        selected = self.map_tree.selection()
        if len(selected) != 1:
            return
        mapping = self.mappings[self.map_tree.index(selected[0])]
        self.map_col.set(mapping.column)
        self.map_sheet.set(mapping.sheet)
        self.map_cell.set(mapping.cell)
        self.update_column_hint()

    def _refresh_mapping_tree(self, select: int | None = None) -> None:
        self.map_tree.delete(*self.map_tree.get_children())
        for mapping in self.mappings:
            self.map_tree.insert(
                "", "end", values=(f"{mapping.column} 列", mapping.sheet, mapping.cell)
            )
        if select is not None:
            children = self.map_tree.get_children()
            if 0 <= select < len(children):
                self.map_tree.selection_set(children[select])
                self.map_tree.focus(children[select])

    def _current_inputs(self) -> tuple[Path, Path, str, str, int, list[Mapping], bool] | None:
        source = Path(self.source_var.get().strip())
        folder = Path(self.folder_var.get().strip())
        if not source.is_file():
            messagebox.showerror("总表", "请先选择总表。")
            return None
        if not folder.is_dir():
            messagebox.showerror("人员文件夹", "请先选择人员文件夹。")
            return None
        if not self.mappings:
            messagebox.showerror("映射", "请至少添加一条列映射。")
            return None
        try:
            name_col = norm_column(self.name_var.get())
        except Exception:
            messagebox.showerror("姓名列", "姓名列请填 A、B、C 这样的列号。")
            return None
        start = self._start_row()
        if start < 1:
            messagebox.showerror("起始行", "起始行必须大于 0。")
            return None
        return source, folder, self.sheet_var.get().strip(), name_col, start, list(self.mappings), self.backup_var.get()

    def preview(self) -> None:
        self._start_job(write=False)

    def write_files(self) -> None:
        inputs = self._current_inputs()
        if inputs is None or self.running:
            return
        _source, _folder, _sheet, name_col, start, mappings, backup = inputs
        detail = "\n".join(f"{item.column} 列 → {item.sheet}!{item.cell}" for item in mappings[:12])
        if len(mappings) > 12:
            detail += "\n…"
        backup_text = "会另存一份 bak 表格（已有的不覆盖）" if backup else "不备份，直接改原文件"
        if not messagebox.askokcancel(
            "确认写入",
            f"用 {name_col} 列从第 {start} 行开始匹配人员，并写入这些位置：\n\n{detail}\n\n{backup_text}",
        ):
            return
        self._start_job(write=True)

    def _start_job(self, write: bool) -> None:
        inputs = self._current_inputs()
        if inputs is None or self.running:
            return
        self.running = True
        self._set_busy(True)
        self.clear_log()
        self.write_log("正在读取…\n")
        thread = threading.Thread(target=self._worker, args=(inputs, write), daemon=True)
        thread.start()

    def _worker(self, inputs, write: bool) -> None:
        source, folder, sheet, name_col, start, mappings, backup = inputs
        try:
            lines, stats = run_fill(
                source, folder, sheet or None, name_col, start, mappings, write, backup
            )
        except Exception as exc:
            lines = [f"出错：{exc}"]
            stats = {"people": 0, "ok": 0, "errors": 1, "warnings": 0}
        self.log_queue.put((lines, stats, write))

    def _poll(self) -> None:
        try:
            lines, stats, write = self.log_queue.get_nowait()
        except queue.Empty:
            self.after(120, self._poll)
            return
        self.running = False
        self._set_busy(False)
        self.clear_log()
        self.write_log("\n".join(lines))
        if write and stats["errors"]:
            messagebox.showwarning(
                "写入结束",
                f"成功 {stats['ok']} 个，有问题 {stats['errors']} 个。请看日志。",
            )
        elif write:
            messagebox.showinfo("写入结束", f"已写入 {stats['ok']} 个文件。")
        self.after(120, self._poll)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.preview_button.configure(state=state)
        self.write_button.configure(state=state)

    def _config_payload(self) -> dict:
        return {
            "source": self.source_var.get().strip(),
            "folder": self.folder_var.get().strip(),
            "source_sheet": self.sheet_var.get().strip(),
            "name_col": self.name_var.get().strip(),
            "start_row": self._start_row(),
            "header": self.header_var.get(),
            "backup": self.backup_var.get(),
            "mappings": [
                {"column": item.column, "sheet": item.sheet, "cell": item.cell}
                for item in self.mappings
            ],
        }

    def save_config(self) -> None:
        path = filedialog.asksaveasfilename(
            title="保存映射配置",
            defaultextension=".json",
            initialfile=CONFIG_NAME,
            initialdir=str(Path(__file__).resolve().parent),
            filetypes=[("配置文件", "*.json")],
        )
        if not path:
            return
        Path(path).write_text(json.dumps(self._config_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
        self.write_log(f"配置已保存：{path}")

    def load_config(self) -> None:
        path = filedialog.askopenfilename(
            title="载入映射配置",
            initialdir=str(Path(__file__).resolve().parent),
            filetypes=[("配置文件", "*.json")],
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            mappings = []
            for item in payload.get("mappings", []):
                mappings.append(
                    Mapping(norm_column(item["column"]), str(item["sheet"]).strip(), norm_cell(item["cell"]))
                )
        except Exception as exc:
            messagebox.showerror("配置", f"这个配置读不了：{exc}")
            return
        self.source_var.set(payload.get("source", ""))
        self.folder_var.set(payload.get("folder", ""))
        self.sheet_var.set(payload.get("source_sheet", ""))
        self.name_var.set(payload.get("name_col", "A"))
        self.start_var.set(int(payload.get("start_row", 1)))
        self.header_var.set(bool(payload.get("header", False)))
        self.backup_var.set(bool(payload.get("backup", True)))
        self.mappings = mappings
        self._refresh_mapping_tree()
        self.reload_source(popup=False)
        self.reload_folder(popup=False)
        self.write_log(f"已载入配置：{path}")


def main() -> None:
    if openpyxl is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("缺少依赖", "请先安装 openpyxl：\npython -m pip install openpyxl")
        root.destroy()
        return
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
