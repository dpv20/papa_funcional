import streamlit as st
from pathlib import Path
import subprocess
from datetime import datetime

from funciones.Trans_excel import render as render_crear_excel  # 👈 usa la vista con 3 botones


# --- Configuración global ---
st.set_page_config(page_title="Construction Budget", layout="wide")
logo_path = Path("media/pavez_P_logo.png")
logo2_path = Path("media/pavez_logo.png")

def render_git_sync_button():
    import subprocess
    from datetime import datetime
    from pathlib import Path

    def _get_git_cmd() -> str | None:
        for c in ["git", r"C:\Program Files\Git\bin\git.exe", r"C:\Program Files (x86)\Git\bin\git.exe"]:
            try:
                r = subprocess.run([c, "--version"], capture_output=True, text=True)
                if r.returncode == 0:
                    return c
            except Exception:
                pass
        return None

    def _find_repo_root(start: Path) -> Path | None:
        p = start.resolve()
        for _ in range(10):
            if (p / ".git").exists():
                return p
            if p.parent == p:
                break
            p = p.parent
        return None

    if st.button("💾 Guardar en la nube", type="primary", use_container_width=True):
        git = _get_git_cmd()
        if not git:
            st.error("Git no está disponible. Verifica instalación y PATH.")
            return

        repo = _find_repo_root(Path(__file__).resolve().parent) or Path(__file__).resolve().parent
        outs: list[str] = []

        def run(cmd: list[str]):
            res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
            outs.append(f"$ {' '.join(cmd)}\n{res.stdout}{res.stderr}")
            return res

        with st.spinner("Sincronizando con GitHub..."):
            # Detectar branch actual (default: main)
            rb = run([git, "rev-parse", "--abbrev-ref", "HEAD"])
            branch = rb.stdout.strip() if rb.returncode == 0 and rb.stdout.strip() else "main"

            run([git, "fetch", "origin"])                      # 1) fetch siempre
            msg = f"Auto-commit {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            run([git, "add", "-A"])                            # 2) add
            rc = run([git, "commit", "-m", msg])               # 2) commit (puede no haber cambios)
            nothing = "nothing to commit" in (rc.stdout + rc.stderr).lower()

            # 3) pull --rebase (asegura fast-forward)
            pr = run([git, "pull", "--rebase", "origin", branch])
            if pr.returncode != 0:
                # Rama sin upstream configurado: la configuramos y reintentamos
                if "There is no tracking information" in (pr.stdout + pr.stderr):
                    run([git, "branch", "--set-upstream-to", f"origin/{branch}", branch])
                    pr = run([git, "pull", "--rebase", "origin", branch])

            # Conflictos
            if pr.returncode != 0 and "CONFLICT" in (pr.stdout + pr.stderr):
                st.error(
                    "Hay conflictos de merge durante el rebase. Resuélvelos y vuelve a intentar.\n"
                    "Pistas: `git status`, edita archivos en conflicto, `git add`, `git rebase --continue`."
                )
                with st.expander("Ver salida de Git"):
                    st.code("\n".join(outs), language="bash")
                return

            # 4) push
            ps = run([git, "push", "origin", branch])
            if ps.returncode == 0:
                if nothing:
                    st.info("No había cambios nuevos, pero la rama quedó sincronizada 👍")
                else:
                    st.success("Cambios enviados a GitHub ✅")
            else:
                st.warning(
                    "Push rechazado por historial remoto. Integra cambios manualmente o, si corresponde, fuerza con "
                    "`git push --force-with-lease` (no recomendado)."
                )

        with st.expander("Ver salida de Git"):
            st.code("\n".join(outs), language="bash")

            
# --- Sidebar ---
with st.sidebar:
    if logo_path.exists():
        st.image(str(logo_path))
    st.title("Menú")

    view = st.radio(
        "Ir a:",
        [
            "🏠 Home",
            "📦 Nuevo Presupuesto",
            "📝 Modificar Presupuesto",
            "➕ Agregar ítem",
            "🛠️ Modificar ítem",
            "🗂️ Categorías",
            "💱 Monedas",
            "📊 Crear Unitario",
            "🧾 Crear Detallado",
        ],
        index=0
    )

    st.divider()
    # Botón de sync Git en la sidebar:
    render_git_sync_button()


# --- Vistas locales ---
def render_home():
    st.title("Bienvenido 👋")
    st.write(
        """
        Esta es tu app de **gestión de presupuesto de construcción**.
        Usa el menú lateral para navegar entre las funciones.
        """
    )
    if logo2_path.exists():
        st.image(str(logo2_path), caption="Pavez")


def render_excel():
    # Delegamos toda la UI de Crear/Mostrar/Descargar al módulo Trans_excel
    render_crear_excel()


# --- Router simple ---
if view == "🏠 Home":
    render_home()

elif view == "📦 Nuevo Presupuesto":
    try:
        from funciones.presupuesto_nuevo import render_presupuesto_nuevo
        render_presupuesto_nuevo()
    except Exception as e:
        st.error(f"No se pudo cargar **Nuevo Presupuesto**: {e}")

elif view == "📝 Modificar Presupuesto":
    try:
        from funciones.modificar_presupuesto import render_modificar_presupuesto
        render_modificar_presupuesto()
    except Exception as e:
        st.error(f"No se pudo cargar **Modificar Presupuesto**: {e}")

elif view == "🛠️ Modificar ítem":
    try:
        from funciones.modify_item import render_modify_item
        render_modify_item()
    except Exception as e:
        st.error(f"No se pudo cargar **Modificar ítem**: {e}")

elif view == "➕ Agregar ítem":
    try:
        from funciones.add_item import render_add_item
        render_add_item()
    except Exception as e:
        st.error(f"No se pudo cargar **Agregar ítem**: {e}")

elif view == "🗂️ Categorías":
    try:
        from funciones.agregar_categoria import render_add_category
        render_add_category()
    except Exception as e:
        st.error(f"No se pudo cargar **Categorías**: {e}")

elif view == "💱 Monedas":
    try:
        from funciones.gestionar_monedas import render_gestionar_monedas
        render_gestionar_monedas()
    except Exception as e:
        st.error(f"No se pudo cargar **Monedas**: {e}")

elif view == "📊 Crear Unitario":
    render_excel()

elif view == "🧾 Crear Detallado":
    try:
        from funciones.crear_detallado import render_crear_detallado
        render_crear_detallado()
    except Exception as e:
        st.error(f"No se pudo cargar **Crear Detallado**: {e}")
