#!/usr/bin/env python3
"""
AGDock - GUI
"""

import os
import sys
import math
import queue
import threading
import traceback
import shutil
import subprocess
import csv
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# --- RDKit Import Check ---
RDKIT_AVAILABLE = True
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
except Exception as e:
    RDKIT_AVAILABLE = False
    RDKIT_ERROR = str(e)


# ---------------------------------------------------------
# --- PyInstaller Resource Helper
# ---------------------------------------------------------
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# ---------------------------------------------------------
# --- Windows Console Hider Helper (THE FIX)
# ---------------------------------------------------------
def get_subprocess_flags():
    """Returns flags to suppress popup windows on Windows."""
    if os.name == 'nt':
        # CREATE_NO_WINDOW = 0x08000000
        return 0x08000000
    return 0


# ---------------------------
# --- Helper functions ------
# ---------------------------
def keep_first_fragment(smiles):
    return smiles.split('.')[0].strip() if '.' in smiles else smiles.strip()


def embed_safe(mol, seed=0xf00d):
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    try:
        return AllChem.EmbedMolecule(mol, params)
    except Exception:
        try:
            return AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        except Exception:
            return -1


def apply_mmff(mol, maxIters=250):
    try:
        if AllChem.MMFFHasAllMoleculeParams(mol):
            AllChem.MMFFOptimizeMolecule(mol, maxIters=maxIters)
            return mol, True
    except Exception:
        pass
    return mol, False


def apply_uff(mol, maxIters=250):
    try:
        AllChem.UFFOptimizeMolecule(mol, maxIters=maxIters)
        return mol, True
    except Exception:
        return mol, False


# ---------------------------
# --- Docking Logic ---------
# ---------------------------
def run_vina(ligand_path, receptor_file, center, size, vina_path, logger=None):
    base_name = os.path.basename(ligand_path).replace(".pdbqt", "")
    out_file = os.path.join(os.path.dirname(ligand_path), base_name + "_docked.pdbqt")
    log_file = os.path.join(os.path.dirname(ligand_path), base_name + "_log.txt")

    if logger:
        logger(f"Docking {base_name}...")

    cmd = [
        vina_path,
        "--receptor", receptor_file,
        "--ligand", ligand_path,
        "--center_x", str(center[0]), "--center_y", str(center[1]), "--center_z", str(center[2]),
        "--size_x", str(size[0]), "--size_y", str(size[1]), "--size_z", str(size[2]),
        "--out", out_file, "--log", log_file
    ]

    try:
        # [FIX] Added creationflags to hide the black window
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=get_subprocess_flags()
        )
    except Exception as e:
        if logger: logger(f"Vina failed: {e}")
        return None, None

    energy = None

    if os.path.exists(out_file):
        try:
            with open(out_file, 'r') as f:
                for line in f:
                    if line.startswith("REMARK VINA RESULT:"):
                        parts = line.split()
                        if len(parts) >= 4:
                            energy = float(parts[3])
                            break
        except Exception as e:
            if logger: logger(f"Error reading PDBQT score: {e}")

    if energy is None and os.path.exists(log_file):
        try:
            with open(log_file, 'r') as f:
                content = f.read()
                match = re.search(r'^\s*1\s+(-?\d+\.\d+)\s+', content, re.MULTILINE)
                if match:
                    energy = float(match.group(1))
        except:
            pass

    if energy is not None:
        if logger: logger(f"Done {base_name}. Score: {energy}")
    else:
        if logger: logger(f"⚠️ Score not found for {base_name}.")

    return energy, out_file


def compute_box_from_residues(receptor_file, residue_list, logger=None):
    coords = []
    try:
        with open(receptor_file, "r") as fh:
            for line in fh:
                if line.startswith("ATOM") or line.startswith("HETATM"):
                    try:
                        resnum_str = line[22:26].strip()
                        resnum = int(''.join(ch for ch in resnum_str if ch.isdigit()))
                        if resnum in residue_list:
                            x = float(line[30:38])
                            y = float(line[38:46])
                            z = float(line[46:54])
                            coords.append((x, y, z))
                    except:
                        continue
    except Exception as e:
        if logger: logger(f"Error reading receptor residues: {e}")
        return None, None

    if not coords:
        if logger: logger("No atoms found for specified residues.")
        return None, None

    xs, ys, zs = zip(*coords)
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)

    center = [
        round((min_x + max_x) / 2.0, 3),
        round((min_y + max_y) / 2.0, 3),
        round((min_z + max_z) / 2.0, 3)
    ]
    PADDING = 12.0
    size = [
        round((max_x - min_x) + PADDING, 3),
        round((max_y - min_y) + PADDING, 3),
        round((max_z - min_z) + PADDING, 3)
    ]
    return center, size


# ---------------------------
# --- Batch Processing ------
# ---------------------------
def process_batch(smiles_list, out_base, energy_choice, receptor_file,
                  center, size, vina_path, progress_cb, logger, stop_event):
    try:
        if not out_base: out_base = os.getcwd()

        pdb_dir = os.path.join(out_base, "pdb")
        pdbqt_dir = os.path.join(out_base, "pdbqt")
        os.makedirs(pdb_dir, exist_ok=True)
        os.makedirs(pdbqt_dir, exist_ok=True)

        summary_csv = os.path.join(out_base, "Docking_Summary.csv")

        if not os.path.exists(summary_csv):
            try:
                with open(summary_csv, 'w', newline='') as f:
                    csv.writer(f).writerow(["Molecule_ID", "Binding affinity", "SMILES"])
            except:
                pass

        total = len(smiles_list)
        ob_cmd = shutil.which("obabel") or shutil.which("openbabel")

        for idx, smi in enumerate(smiles_list, 1):
            if stop_event.is_set(): break

            smi_clean = keep_first_fragment(smi)
            mol = Chem.MolFromSmiles(smi_clean)
            base_name = f"Mol_{idx}"
            current_score = "N/A"

            if mol is None:
                logger(f"[{idx}/{total}] Invalid SMILES: {smi_clean}")
                progress_cb(idx, total)
                continue

            try:
                Chem.SanitizeMol(mol)
            except:
                pass

            mol = Chem.AddHs(mol)
            if embed_safe(mol) < 0:
                try:
                    AllChem.EmbedMolecule(mol)
                except:
                    pass

            logger(f"[{idx}/{total}] Processing: {smi_clean}")

            if energy_choice == "MMFF94":
                apply_mmff(mol)
            elif energy_choice == "UFF":
                apply_uff(mol)

            pdb_path = os.path.join(pdb_dir, f"{base_name}.pdb")
            try:
                Chem.MolToPDBFile(mol, pdb_path)
            except Exception as e:
                logger(f"Error saving PDB: {e}")
                progress_cb(idx, total)
                continue

            pdbqt_path = os.path.join(pdbqt_dir, f"{base_name}.pdbqt")
            if ob_cmd:
                try:
                    # [FIX] Added creationflags to hide the black window for OpenBabel too
                    res = subprocess.run(
                        [ob_cmd, pdb_path, "-O", pdbqt_path, "--partialcharge", "gasteiger"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        creationflags=get_subprocess_flags()
                    )

                    if res.returncode == 0 and os.path.exists(pdbqt_path):
                        if receptor_file and vina_path:
                            energy, out_file = run_vina(pdbqt_path, receptor_file, center, size, vina_path, logger)
                            if energy is not None:
                                current_score = energy
                            else:
                                logger("Docking ran but no score returned.")
                    else:
                        logger(f"OpenBabel conversion failed for {base_name}")
                except Exception as e:
                    logger(f"Error during OpenBabel/Vina: {e}")
            else:
                logger("OpenBabel not found. Install OpenBabel.")

            try:
                with open(summary_csv, 'a', newline='') as f:
                    csv.writer(f).writerow([base_name, current_score, smi_clean])
            except:
                pass

            progress_cb(idx, total)

        logger("Docking completed successfully. Check the output folder.", fg="#008000")

    except Exception as e:
        logger(f"Fatal Error: {e}")
        logger(traceback.format_exc())


# ---------------------------
# --- GUI --------------------
# ---------------------------
class OneClickDockApp:
    def __init__(self, root):
        self.root = root
        self.stop_event = threading.Event()

        # Window Setup
        self._fixed_w, self._fixed_h = 920, 520
        root.title("AGDock")
        root.geometry(f"{self._fixed_w}x{self._fixed_h}")
        root.resizable(False, False)

        # --------------------------------------------------------
        # --- ICON LOADING
        # --------------------------------------------------------
        try:
            icon_file = resource_path("AGDock_Code.ico")
            root.iconbitmap(icon_file)
        except Exception as e:
            print(f"Icon warning: {e}")
        # --------------------------------------------------------

        self._msg_queue = queue.Queue()
        self.root.after(100, self._flush_queue)

        # ---------------- HEADER ----------------
        title_frame = tk.Frame(root, bg="#f0f0f0")
        title_frame.pack(fill="x", pady=(10, 5))
        tk.Label(title_frame, text="AGDock", font=("Inter", 16, "bold"), bg="#f0f0f0").pack()
        tk.Label(title_frame, text="SysBioP Lab || Molecular Biology & Bioinformatics || Tripura University",
                 font=("Segoe UI", 10,), fg="#000000", bg="#f0f0f0").pack()

        # ---------------- MAIN CONTENT ----------------
        content_frame = tk.Frame(root)
        content_frame.pack(fill="both", expand=True, padx=15, pady=5)

        # LEFT COLUMN
        left_frame = tk.Frame(content_frame)
        left_frame.pack(side="left", fill="y", padx=(0, 10), anchor="n")

        # --> GROUP 1: INPUT FILES
        group1 = tk.LabelFrame(left_frame, text="1. Input & Settings", font=("Segoe UI", 10, "bold"), padx=10, pady=10)
        group1.pack(fill="x", pady=(0, 10))
        group1.columnconfigure(1, weight=1)

        self.mk_grid_entry(group1, 0, "SMILES File:", "browse_file", "entry_file")
        self.mk_grid_entry(group1, 1, "Output Folder:", "browse_out", "entry_out")

        tk.Label(group1, text="Minimization:", anchor="w").grid(row=2, column=0, sticky="w", pady=5)
        self.energy_cb = ttk.Combobox(group1, values=["None", "MMFF94", "UFF"], state="readonly")
        self.energy_cb.current(1)
        self.energy_cb.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        # --> GROUP 2: DOCKING
        group2 = tk.LabelFrame(left_frame, text="2. Docking Setup", font=("Segoe UI", 10, "bold"), padx=10,
                               pady=10)
        group2.pack(fill="x", pady=0)
        group2.columnconfigure(1, weight=1)

        self.mk_grid_entry(group2, 0, "Receptor (.pdbqt):", "browse_rec", "entry_rec")
        self.mk_grid_entry(group2, 1, "Vina Executable:", "browse_vina", "entry_vina")

        tk.Label(group2, text="Active Site Residues:", fg="#000000", anchor="w").grid(row=2, column=0, sticky="w",
                                                                                      pady=(10, 0))
        tk.Label(group2, text="(e.g., 10,20,30 )", font=("Segoe UI", 8), fg="#000000").grid(row=2,
                                                                                            column=1,
                                                                                            sticky="w",
                                                                                            pady=(10,
                                                                                                  0))
        self.entry_residues = tk.Entry(group2)
        self.entry_residues.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(2, 5))

        # --> ACTION BUTTONS
        btn_frame = tk.Frame(left_frame)
        btn_frame.pack(fill="x", pady=20)

        start_btn = tk.Button(btn_frame, text="START DOCKING", bg="#28a745", fg="white",
                              font=("Segoe UI", 10, "bold"), height=2, command=self.start)
        start_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

        kill_btn = tk.Button(btn_frame, text="STOP", bg="#dc3545", fg="white",
                             font=("Segoe UI", 10, "bold"), height=2, width=10, command=self.stop_event.set)
        kill_btn.pack(side="right")

        # RIGHT COLUMN: LOG
        right_frame = tk.LabelFrame(content_frame, text="Process Log", font=("Segoe UI", 10, "bold"), padx=5, pady=5)
        right_frame.pack(side="right", fill="both", expand=True)

        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)

        log_scroll = tk.Scrollbar(right_frame)
        log_scroll.grid(row=0, column=1, sticky="ns")

        self.text_log = tk.Text(right_frame, wrap="word", state="disabled", font=("Consolas", 9),
                                yscrollcommand=log_scroll.set, bg="#fdfdfd")
        self.text_log.grid(row=0, column=0, sticky="nsew")

        log_scroll.config(command=self.text_log.yview)

        self.progress = ttk.Progressbar(right_frame, orient="horizontal", mode="determinate")
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))

    def mk_grid_entry(self, parent, r, lbl, cmd, attr):
        tk.Label(parent, text=lbl, anchor="w").grid(row=r, column=0, sticky="w", pady=5)
        e = tk.Entry(parent, width=30)
        e.grid(row=r, column=1, sticky="ew", padx=5, pady=5)
        setattr(self, attr, e)
        tk.Button(parent, text="Browse", width=8, command=getattr(self, cmd)).grid(row=r, column=2, padx=0, pady=5)

    def browse_file(self):
        self._browse(self.entry_file, [("Text", "*.txt")])

    def browse_out(self):
        self._browse_dir(self.entry_out)

    def browse_rec(self):
        self._browse(self.entry_rec, [("PDBQT", "*.pdbqt")])

    def browse_vina(self):
        self._browse(self.entry_vina, [("Exec", "*")])

    def _browse(self, entry, ft):
        p = filedialog.askopenfilename(filetypes=ft)
        if p: entry.delete(0, "end"); entry.insert(0, p)

    def _browse_dir(self, entry):
        p = filedialog.askdirectory()
        if p: entry.delete(0, "end"); entry.insert(0, p)

    # Logging
    def _flush_queue(self):
        try:
            while True:
                item = self._msg_queue.get_nowait()
                typ = item[0]

                if typ == "log":
                    text = item[1]
                    color = item[2] if len(item) > 2 else "black"

                    self.text_log.configure(state="normal")
                    tag_name = f"color_{color}"
                    self.text_log.tag_config(tag_name, foreground=color)
                    self.text_log.insert("end", text + "\n", tag_name)
                    self.text_log.see("end")
                    self.text_log.configure(state="disabled")

                elif typ == "progress":
                    val = item[1]
                    self.progress["value"] = val
        except queue.Empty:
            pass
        self.root.after(100, self._flush_queue)

    def log(self, m, fg="black"):
        self._msg_queue.put(("log", str(m), fg))

    def progress_cb(self, i, t):
        self._msg_queue.put(("progress", int((i / t) * 100)))

    # Start Action
    def start(self):
        self.stop_event.clear()
        if not self.entry_file.get() or not self.entry_out.get():
            messagebox.showerror("Error", "Missing Input/Output paths");
            return
        if not self.entry_rec.get() or not self.entry_vina.get():
            messagebox.showerror("Error", "Missing Vina or Receptor");
            return
        if not self.entry_residues.get():
            messagebox.showerror("Error", "Missing Residues");
            return

        try:
            res = [int(x) for x in self.entry_residues.get().split(",") if x.strip().isdigit()]
        except:
            messagebox.showerror("Error", "Invalid Residue Format (Use: 1,8,11)");
            return

        self.log("Calculating box from residues...")
        c, s = compute_box_from_residues(self.entry_rec.get(), res, self.log)
        if not c:
            messagebox.showerror("Error", "Oops! I searched everywhere, but those residue numbers don’t exist");
            return
        self.log(f"Box Center: {c}")
        self.log(f"Box Size:   {s}")

        with open(self.entry_file.get()) as f:
            sm = [l.strip() for l in f if l.strip()]

        args = (sm, self.entry_out.get(), self.energy_cb.get(),
                self.entry_rec.get(), c, s, self.entry_vina.get(),
                self.progress_cb, self.log, self.stop_event)

        threading.Thread(target=process_batch, args=args, daemon=True).start()


def main():
    root = tk.Tk()
    if not RDKIT_AVAILABLE:
        messagebox.showerror("RDKit Missing", f"RDKit is not installed or failed to load.\n\nError: {RDKIT_ERROR}")
        root.destroy()
        return
    app = OneClickDockApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()