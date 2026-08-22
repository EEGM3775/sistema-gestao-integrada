#!/usr/bin/env python3
"""
Interface gráfica para remove_marca_dagua.py

Abra um PDF, o programa diagnostica sozinho e lista tudo que pode ser
a marca d'água. Clique no candidato e mande remover.

Build do .exe:
    pip install pyinstaller
    pyinstaller --onefile --windowed --name RemoveMarcaDagua marca_dagua_gui.py
"""

import io
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from contextlib import redirect_stdout
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import fitz

import remove_marca_dagua as motor

# Drag-and-drop é opcional: sem tkinterdnd2 o app usa só o botão "Abrir PDF".
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    RAIZ = TkinterDnD.Tk
    TEM_DND = True
except ImportError:
    RAIZ = tk.Tk
    TEM_DND = False


# Quanto menor, mais acima na lista. Texto inclinado é o suspeito mais comum.
PRIORIDADE = {"texto": 0, "camada": 1, "anotacoes": 2, "xobject": 3, "imagem": 4}

ROTULO = {
    "texto": "Texto inclinado",
    "camada": "Camada (OCG)",
    "anotacoes": "Anotação",
    "xobject": "XObject",
    "imagem": "Imagem",
}


def escanear(caminho):
    """Devolve os candidatos a marca d'água, deduplicados entre páginas."""
    doc = fitz.open(caminho)
    achados = {}

    def registrar(tipo, alvo, detalhe, pagina=None):
        chave = (tipo, str(alvo))
        item = achados.setdefault(
            chave,
            {"tipo": tipo, "alvo": alvo, "detalhe": detalhe, "paginas": []},
        )
        if pagina is not None and pagina not in item["paginas"]:
            item["paginas"].append(pagina)

    for xref, info in (doc.get_ocgs() or {}).items():
        if info.get("name"):
            registrar("camada", info["name"], info["name"])

    for n, page in enumerate(doc, start=1):
        for a in page.annots() or []:
            if a.type[1] in ("Watermark", "Stamp", "FreeText"):
                registrar("anotacoes", a.type[1], f"tipo {a.type[1]}", n)

        for xo in page.get_xobjects():
            registrar("xobject", xo[1], f"/{xo[1]}", n)

        for img in page.get_images(full=True):
            registrar("imagem", img[0], f"xref {img[0]} — {img[2]}x{img[3]}px", n)

        for bloco in page.get_text("dict")["blocks"]:
            for linha in bloco.get("lines", []):
                if abs(linha["dir"][1]) > 0.01:  # não é horizontal
                    txt = "".join(s["text"] for s in linha["spans"]).strip()
                    if txt:
                        registrar("texto", txt, repr(txt), n)

    doc.close()

    itens = list(achados.values())
    itens.sort(key=lambda c: (PRIORIDADE[c["tipo"]], c["detalhe"]))
    return itens


def remover(candidato, entrada, saida):
    """Executa a operação certa e devolve o que o motor imprimiu."""
    tipo, alvo = candidato["tipo"], candidato["alvo"]
    buf = io.StringIO()
    with redirect_stdout(buf):
        if tipo == "texto":
            motor.remover_texto(entrada, saida, alvo)
        elif tipo == "xobject":
            motor.remover_xobject(entrada, saida, alvo)
        elif tipo == "camada":
            motor.remover_camada(entrada, saida, alvo)
        elif tipo == "anotacoes":
            motor.remover_anotacoes(entrada, saida)
        elif tipo == "imagem":
            motor.remover_imagem(entrada, saida, int(alvo))
    return buf.getvalue().strip()


class App:
    def __init__(self, raiz):
        self.raiz = raiz
        self.pdf = None
        self.candidatos = []
        self.fila = queue.Queue()

        raiz.title("Remover marca d'água de PDF")
        raiz.geometry("760x520")
        raiz.minsize(640, 440)

        self._montar()
        self.raiz.after(100, self._drenar_fila)

    # ------------------------------------------------------------- interface
    def _montar(self):
        pad = {"padx": 12, "pady": 6}

        topo = ttk.Frame(self.raiz)
        topo.pack(fill="x", **pad)

        dica = "Arraste um PDF aqui ou clique em Abrir" if TEM_DND else "Clique em Abrir para escolher o PDF"
        self.rotulo_arquivo = ttk.Label(topo, text=dica, foreground="#666")
        self.rotulo_arquivo.pack(side="left", fill="x", expand=True)

        ttk.Button(topo, text="Abrir PDF…", command=self.escolher).pack(side="right")

        if TEM_DND:
            self.raiz.drop_target_register(DND_FILES)
            self.raiz.dnd_bind("<<Drop>>", self._soltou)

        ttk.Label(self.raiz, text="Candidatos encontrados — selecione o que é a marca:").pack(
            anchor="w", padx=12
        )

        quadro = ttk.Frame(self.raiz)
        quadro.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        self.lista = ttk.Treeview(
            quadro, columns=("tipo", "detalhe", "paginas"), show="headings", selectmode="browse"
        )
        self.lista.heading("tipo", text="Tipo")
        self.lista.heading("detalhe", text="Detalhe")
        self.lista.heading("paginas", text="Páginas")
        self.lista.column("tipo", width=130, stretch=False)
        self.lista.column("paginas", width=90, stretch=False, anchor="center")
        self.lista.pack(side="left", fill="both", expand=True)
        self.lista.bind("<Double-1>", lambda _e: self.remover_selecionado())

        barra = ttk.Scrollbar(quadro, orient="vertical", command=self.lista.yview)
        barra.pack(side="right", fill="y")
        self.lista.configure(yscrollcommand=barra.set)

        acoes = ttk.Frame(self.raiz)
        acoes.pack(fill="x", **pad)

        self.botao_remover = ttk.Button(
            acoes, text="Remover selecionado", command=self.remover_selecionado, state="disabled"
        )
        self.botao_remover.pack(side="left")

        self.botao_pasta = ttk.Button(
            acoes, text="Abrir pasta do resultado", command=self.abrir_pasta, state="disabled"
        )
        self.botao_pasta.pack(side="left", padx=(8, 0))

        self.status = tk.Text(self.raiz, height=6, wrap="word", state="disabled",
                              background="#f6f6f6", relief="flat")
        self.status.pack(fill="x", padx=12, pady=(0, 12))

        self.ultimo_resultado = None

    def _log(self, msg):
        self.status.configure(state="normal")
        self.status.insert("end", msg + "\n")
        self.status.see("end")
        self.status.configure(state="disabled")

    # --------------------------------------------------------------- entrada
    def _soltou(self, evento):
        # O Tk devolve o caminho entre chaves quando há espaços.
        caminho = evento.data.strip().strip("{}")
        self.carregar(caminho)

    def escolher(self):
        caminho = filedialog.askopenfilename(
            title="Escolha o PDF", filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")]
        )
        if caminho:
            self.carregar(caminho)

    def carregar(self, caminho):
        if not caminho.lower().endswith(".pdf"):
            messagebox.showwarning("Arquivo inválido", "Selecione um arquivo .pdf")
            return

        self.pdf = caminho
        self.rotulo_arquivo.configure(text=os.path.basename(caminho), foreground="black")
        self.lista.delete(*self.lista.get_children())
        self.botao_remover.configure(state="disabled")
        self._log(f"Analisando {os.path.basename(caminho)}…")

        threading.Thread(target=self._escanear_thread, args=(caminho,), daemon=True).start()

    def _escanear_thread(self, caminho):
        try:
            self.fila.put(("scan_ok", escanear(caminho)))
        except Exception as e:
            self.fila.put(("erro", f"Falha ao ler o PDF: {e}"))

    # ---------------------------------------------------------------- remoção
    def remover_selecionado(self):
        sel = self.lista.selection()
        if not self.pdf or not sel:
            return

        candidato = self.candidatos[int(sel[0])]
        origem = Path(self.pdf)
        sugestao = f"{origem.stem}_sem_marca.pdf"

        destino = filedialog.asksaveasfilename(
            title="Salvar como",
            defaultextension=".pdf",
            initialfile=sugestao,
            initialdir=str(origem.parent),
            filetypes=[("PDF", "*.pdf")],
        )
        if not destino:
            return

        self.botao_remover.configure(state="disabled")
        self._log(f"Removendo: {ROTULO[candidato['tipo']]} — {candidato['detalhe']}")
        threading.Thread(
            target=self._remover_thread, args=(candidato, self.pdf, destino), daemon=True
        ).start()

    def _remover_thread(self, candidato, entrada, saida):
        try:
            self.fila.put(("remove_ok", (remover(candidato, entrada, saida), saida)))
        except Exception as e:
            self.fila.put(("erro", f"Falha na remoção: {e}"))

    def abrir_pasta(self):
        if self.ultimo_resultado:
            subprocess.run(["explorer", "/select,", os.path.normpath(self.ultimo_resultado)])

    # ------------------------------------------------- ponte thread -> Tkinter
    def _drenar_fila(self):
        try:
            while True:
                tipo, dado = self.fila.get_nowait()

                if tipo == "scan_ok":
                    self.candidatos = dado
                    for i, c in enumerate(dado):
                        paginas = ", ".join(map(str, c["paginas"])) or "—"
                        self.lista.insert(
                            "", "end", iid=str(i),
                            values=(ROTULO[c["tipo"]], c["detalhe"], paginas),
                        )
                    if dado:
                        self.lista.selection_set("0")
                        self.botao_remover.configure(state="normal")
                        self._log(f"{len(dado)} candidato(s). O primeiro costuma ser a marca.")
                    else:
                        self._log("Nenhum candidato encontrado neste PDF.")

                elif tipo == "remove_ok":
                    saida_txt, caminho = dado
                    self.ultimo_resultado = caminho
                    self._log(saida_txt or "Concluído.")
                    if saida_txt.startswith("0 "):
                        self._log(
                            "Nada casou. A fonte provavelmente é subsetada — "
                            "tente o XObject ou a camada em vez do texto."
                        )
                    self.botao_remover.configure(state="normal")
                    self.botao_pasta.configure(state="normal")

                elif tipo == "erro":
                    self._log(dado)
                    self.botao_remover.configure(state="normal")
                    messagebox.showerror("Erro", dado)

        except queue.Empty:
            pass
        self.raiz.after(100, self._drenar_fila)


if __name__ == "__main__":
    raiz = RAIZ()
    app = App(raiz)
    if len(sys.argv) > 1:  # permite arrastar o PDF sobre o ícone do .exe
        raiz.after(200, lambda: app.carregar(sys.argv[1]))
    raiz.mainloop()
