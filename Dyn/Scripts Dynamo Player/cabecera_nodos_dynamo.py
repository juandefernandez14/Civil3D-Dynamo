# -*- coding: utf-8 -*-
# =============================================================================
# CABECERA COMUN - Pipeline - v02
#
# Este fichero NO se ejecuta tal cual: contiene los DOS snippets que se
# pegan en dos Python Script nodes NUEVOS de cada .dyn, mas utilidades
# one-off. El trabajo pesado vive en pipeline.py (un solo fichero que se
# mantiene en un unico sitio); estos snippets solo lo invocan.
#
# NO HAY RUTAS QUE EDITAR. Cada snippet localiza pipeline.py solo:
#   1) instalado con instalar.bat (Python interno de Dynamo)   <- recomendado
#   2) variable de entorno PIPELINE_HOME
#   3) carpeta del proyecto (hasta 3 niveles por encima del DWG activo)
# Si no lo encuentra, el propio nodo devuelve un KO con las rutas probadas.
#
# v02: eliminada la lista RUTAS_MODULO; localizador unico sin rutas fijas.
# =============================================================================


# =============================================================================
# SNIPPET A  ->  nodo "CONFIG"
# -----------------------------------------------------------------------------
# Pegar en un Python Script node NUEVO al PRINCIPIO del grafo.
# - Su OUT es una lista: [ok, log, carpeta, firma, p1, p2, ...]
#   con los parametros en el orden fijo de PARAMS_FASE (ver README).
# - Recablear los puertos que hoy vienen de sliders/code blocks a
#   List.GetItemAtIndex(OUT, i) o a un code block  res[i];
# - Conectar OUT[1] (el log) a un Watch grande (WatchWidth 950 /
#   WatchHeight 600).
# - Conectar OUT (entero o un item) como barrera de sincronizacion del
#   primer nodo de trabajo para forzar que esto corra ANTES.
# - No ejecutar el script si OUT[0] es False: el log dice que falta.
# =============================================================================

import os
import sys
import importlib

# ---------------------------------------------------------------------------
# Localizador del modulo pipeline.py. Sin rutas escritas: prueba, en orden,
#   1) ya importable (instalado con instalar.bat en el Python de Dynamo)
#   2) variable de entorno PIPELINE_HOME (carpeta que contiene pipeline.py)
#   3) carpeta del proyecto: subiendo hasta 3 niveles desde el DWG activo
#      (el mismo criterio con el que se localiza config_proyecto.xlsx)
# Si ninguna funciona, OUT es un KO legible con las rutas probadas.
# ---------------------------------------------------------------------------
def _cargar_pipeline():
    probadas = []
    try:
        import pipeline as _m
        importlib.reload(_m)
        return _m, "pipeline.py: importado desde " + str(getattr(_m, "__file__", "?"))
    except ImportError:
        probadas.append("import directo (site-packages de Dynamo)")
    candidatas = []
    ph = os.environ.get("PIPELINE_HOME", "")
    if ph:
        candidatas.append(ph)
    try:
        import clr
        clr.AddReference("AcMgd")
        from Autodesk.AutoCAD.ApplicationServices import Application as _A
        _doc = _A.DocumentManager.MdiActiveDocument
        if _doc is not None:
            _c = os.path.dirname(os.path.abspath(str(_doc.Name)))
            for _ in range(3):
                candidatas.append(_c)
                _p = os.path.dirname(_c)
                if _p == _c:
                    break
                _c = _p
    except Exception as ex:
        probadas.append("DWG activo no disponible: " + str(ex)[:80])
    for _r in candidatas:
        probadas.append(_r)
        if _r and os.path.exists(os.path.join(_r, "pipeline.py")):
            if _r not in sys.path:
                sys.path.insert(0, _r)
            import pipeline as _m
            importlib.reload(_m)
            return _m, "pipeline.py: cargado desde " + _r
    log = ["KO: no se encontro pipeline.py. Rutas probadas:"]
    log += ["  - " + p for p in probadas]
    log.append("Solucion: doble clic en instalar.bat, o copia pipeline.py a la")
    log.append("carpeta del proyecto (junto a config_proyecto.xlsx), o define")
    log.append("la variable de entorno PIPELINE_HOME con su carpeta.")
    return None, "\n".join(log)


pipeline, _msg_carga = _cargar_pipeline()
if pipeline is None:
    OUT = [False, _msg_carga]
else:
    FASE = "3"                            # <- CAMBIAR por la fase de este script
    OUT = pipeline.nodo_config(FASE)
    OUT[1] = _msg_carga + "\n" + OUT[1]


# =============================================================================
# SNIPPET B  ->  nodo "CIERRE"
# -----------------------------------------------------------------------------
# Pegar en un Python Script node NUEVO al FINAL del grafo, despues del
# nodo que hoy produce el log del script.
#
#   IN[0] : str        fase ("0".."7")
#   IN[1] : str        log del script (el mismo string que va al Watch)
#   IN[2] : dict/str   resultados resumidos, ej {"ejes": 203, "kos": 0}
#                      (tambien acepta JSON en texto, o None)
#   IN[3] : bool       aplicado  True = se aplico de verdad (APLICAR)
#                                False = dry-run (no invalida nada)
#   IN[4] : bool       ok        veredicto del script
#   IN[5] : str        auditoria_z  "OK" / "KO" / "N/A"
#   IN[6] : any        BARRERA de sincronizacion: conectar el output del
#                      ultimo nodo de trabajo; el contenido se ignora.
#
#   OUT = [ok_cierre, log_completo]
#   Conectar OUT[1] al Watch grande final (950x600).
# =============================================================================

import os
import sys
import importlib

# ---------------------------------------------------------------------------
# Localizador del modulo pipeline.py. Sin rutas escritas: prueba, en orden,
#   1) ya importable (instalado con instalar.bat en el Python de Dynamo)
#   2) variable de entorno PIPELINE_HOME (carpeta que contiene pipeline.py)
#   3) carpeta del proyecto: subiendo hasta 3 niveles desde el DWG activo
#      (el mismo criterio con el que se localiza config_proyecto.xlsx)
# Si ninguna funciona, OUT es un KO legible con las rutas probadas.
# ---------------------------------------------------------------------------
def _cargar_pipeline():
    probadas = []
    try:
        import pipeline as _m
        importlib.reload(_m)
        return _m, "pipeline.py: importado desde " + str(getattr(_m, "__file__", "?"))
    except ImportError:
        probadas.append("import directo (site-packages de Dynamo)")
    candidatas = []
    ph = os.environ.get("PIPELINE_HOME", "")
    if ph:
        candidatas.append(ph)
    try:
        import clr
        clr.AddReference("AcMgd")
        from Autodesk.AutoCAD.ApplicationServices import Application as _A
        _doc = _A.DocumentManager.MdiActiveDocument
        if _doc is not None:
            _c = os.path.dirname(os.path.abspath(str(_doc.Name)))
            for _ in range(3):
                candidatas.append(_c)
                _p = os.path.dirname(_c)
                if _p == _c:
                    break
                _c = _p
    except Exception as ex:
        probadas.append("DWG activo no disponible: " + str(ex)[:80])
    for _r in candidatas:
        probadas.append(_r)
        if _r and os.path.exists(os.path.join(_r, "pipeline.py")):
            if _r not in sys.path:
                sys.path.insert(0, _r)
            import pipeline as _m
            importlib.reload(_m)
            return _m, "pipeline.py: cargado desde " + _r
    log = ["KO: no se encontro pipeline.py. Rutas probadas:"]
    log += ["  - " + p for p in probadas]
    log.append("Solucion: doble clic en instalar.bat, o copia pipeline.py a la")
    log.append("carpeta del proyecto (junto a config_proyecto.xlsx), o define")
    log.append("la variable de entorno PIPELINE_HOME con su carpeta.")
    return None, "\n".join(log)


pipeline, _msg_carga = _cargar_pipeline()
if pipeline is None:
    OUT = [False, _msg_carga + "\n" + (str(IN[1]) if IN[1] is not None else "")]
else:
    def _abool(v):
        # Acepta booleanos y toggles en texto ("S"/"N", "SI", "TRUE", "1")
        if isinstance(v, str):
            return v.strip().upper() in ("S", "SI", "TRUE", "1", "V")
        return bool(v)

    fase = str(IN[0])
    log_script = IN[1] if IN[1] is not None else ""
    resultados = IN[2]
    aplicado = _abool(IN[3]) if IN[3] is not None else False
    ok_script = _abool(IN[4]) if IN[4] is not None else True
    auditoria = str(IN[5]) if IN[5] is not None else "N/A"
    # IN[6]: barrera de sincronizacion (ignorada)

    OUT = pipeline.nodo_cierre(fase, log_script,
                               resultados=resultados,
                               aplicado=aplicado,
                               ok=ok_script,
                               auditoria_z=auditoria)


# =============================================================================
# UTILIDAD 1  ->  crear la config de un proyecto nuevo en JSON (one-off)
# Pegar en un Python node suelto, ejecutar UNA vez y borrar el nodo.
# =============================================================================

import os
import sys
import importlib

# ---------------------------------------------------------------------------
# Localizador del modulo pipeline.py. Sin rutas escritas: prueba, en orden,
#   1) ya importable (instalado con instalar.bat en el Python de Dynamo)
#   2) variable de entorno PIPELINE_HOME (carpeta que contiene pipeline.py)
#   3) carpeta del proyecto: subiendo hasta 3 niveles desde el DWG activo
#      (el mismo criterio con el que se localiza config_proyecto.xlsx)
# Si ninguna funciona, OUT es un KO legible con las rutas probadas.
# ---------------------------------------------------------------------------
def _cargar_pipeline():
    probadas = []
    try:
        import pipeline as _m
        importlib.reload(_m)
        return _m, "pipeline.py: importado desde " + str(getattr(_m, "__file__", "?"))
    except ImportError:
        probadas.append("import directo (site-packages de Dynamo)")
    candidatas = []
    ph = os.environ.get("PIPELINE_HOME", "")
    if ph:
        candidatas.append(ph)
    try:
        import clr
        clr.AddReference("AcMgd")
        from Autodesk.AutoCAD.ApplicationServices import Application as _A
        _doc = _A.DocumentManager.MdiActiveDocument
        if _doc is not None:
            _c = os.path.dirname(os.path.abspath(str(_doc.Name)))
            for _ in range(3):
                candidatas.append(_c)
                _p = os.path.dirname(_c)
                if _p == _c:
                    break
                _c = _p
    except Exception as ex:
        probadas.append("DWG activo no disponible: " + str(ex)[:80])
    for _r in candidatas:
        probadas.append(_r)
        if _r and os.path.exists(os.path.join(_r, "pipeline.py")):
            if _r not in sys.path:
                sys.path.insert(0, _r)
            import pipeline as _m
            importlib.reload(_m)
            return _m, "pipeline.py: cargado desde " + _r
    log = ["KO: no se encontro pipeline.py. Rutas probadas:"]
    log += ["  - " + p for p in probadas]
    log.append("Solucion: doble clic en instalar.bat, o copia pipeline.py a la")
    log.append("carpeta del proyecto (junto a config_proyecto.xlsx), o define")
    log.append("la variable de entorno PIPELINE_HOME con su carpeta.")
    return None, "\n".join(log)


pipeline, _msg_carga = _cargar_pipeline()
if pipeline is None:
    OUT = _msg_carga
else:
    CARPETA_PROYECTO = r"C:\...\OneDrive\Proyectos\Estera"   # <- CAMBIAR
    NOMBRE_PROYECTO = "Estera"                               # <- CAMBIAR
    OUT = pipeline.crear_config_plantilla(CARPETA_PROYECTO, NOMBRE_PROYECTO)


# =============================================================================
# UTILIDAD 2  ->  aprobar una fase APLICADA (la puerta manual de hoy;
#                 con la paleta C# sera un boton)
# =============================================================================

import os
import sys
import importlib

# ---------------------------------------------------------------------------
# Localizador del modulo pipeline.py. Sin rutas escritas: prueba, en orden,
#   1) ya importable (instalado con instalar.bat en el Python de Dynamo)
#   2) variable de entorno PIPELINE_HOME (carpeta que contiene pipeline.py)
#   3) carpeta del proyecto: subiendo hasta 3 niveles desde el DWG activo
#      (el mismo criterio con el que se localiza config_proyecto.xlsx)
# Si ninguna funciona, OUT es un KO legible con las rutas probadas.
# ---------------------------------------------------------------------------
def _cargar_pipeline():
    probadas = []
    try:
        import pipeline as _m
        importlib.reload(_m)
        return _m, "pipeline.py: importado desde " + str(getattr(_m, "__file__", "?"))
    except ImportError:
        probadas.append("import directo (site-packages de Dynamo)")
    candidatas = []
    ph = os.environ.get("PIPELINE_HOME", "")
    if ph:
        candidatas.append(ph)
    try:
        import clr
        clr.AddReference("AcMgd")
        from Autodesk.AutoCAD.ApplicationServices import Application as _A
        _doc = _A.DocumentManager.MdiActiveDocument
        if _doc is not None:
            _c = os.path.dirname(os.path.abspath(str(_doc.Name)))
            for _ in range(3):
                candidatas.append(_c)
                _p = os.path.dirname(_c)
                if _p == _c:
                    break
                _c = _p
    except Exception as ex:
        probadas.append("DWG activo no disponible: " + str(ex)[:80])
    for _r in candidatas:
        probadas.append(_r)
        if _r and os.path.exists(os.path.join(_r, "pipeline.py")):
            if _r not in sys.path:
                sys.path.insert(0, _r)
            import pipeline as _m
            importlib.reload(_m)
            return _m, "pipeline.py: cargado desde " + _r
    log = ["KO: no se encontro pipeline.py. Rutas probadas:"]
    log += ["  - " + p for p in probadas]
    log.append("Solucion: doble clic en instalar.bat, o copia pipeline.py a la")
    log.append("carpeta del proyecto (junto a config_proyecto.xlsx), o define")
    log.append("la variable de entorno PIPELINE_HOME con su carpeta.")
    return None, "\n".join(log)


pipeline, _msg_carga = _cargar_pipeline()
if pipeline is None:
    OUT = _msg_carga
else:
    OUT = pipeline.aprobar_fase("3")   # <- fase a aprobar


# =============================================================================
# UTILIDAD 3  ->  autotest del modulo en tu maquina (offline, sin tocar
#                 ningun proyecto: trabaja en una carpeta temporal)
# =============================================================================

import os
import sys
import importlib

# ---------------------------------------------------------------------------
# Localizador del modulo pipeline.py. Sin rutas escritas: prueba, en orden,
#   1) ya importable (instalado con instalar.bat en el Python de Dynamo)
#   2) variable de entorno PIPELINE_HOME (carpeta que contiene pipeline.py)
#   3) carpeta del proyecto: subiendo hasta 3 niveles desde el DWG activo
#      (el mismo criterio con el que se localiza config_proyecto.xlsx)
# Si ninguna funciona, OUT es un KO legible con las rutas probadas.
# ---------------------------------------------------------------------------
def _cargar_pipeline():
    probadas = []
    try:
        import pipeline as _m
        importlib.reload(_m)
        return _m, "pipeline.py: importado desde " + str(getattr(_m, "__file__", "?"))
    except ImportError:
        probadas.append("import directo (site-packages de Dynamo)")
    candidatas = []
    ph = os.environ.get("PIPELINE_HOME", "")
    if ph:
        candidatas.append(ph)
    try:
        import clr
        clr.AddReference("AcMgd")
        from Autodesk.AutoCAD.ApplicationServices import Application as _A
        _doc = _A.DocumentManager.MdiActiveDocument
        if _doc is not None:
            _c = os.path.dirname(os.path.abspath(str(_doc.Name)))
            for _ in range(3):
                candidatas.append(_c)
                _p = os.path.dirname(_c)
                if _p == _c:
                    break
                _c = _p
    except Exception as ex:
        probadas.append("DWG activo no disponible: " + str(ex)[:80])
    for _r in candidatas:
        probadas.append(_r)
        if _r and os.path.exists(os.path.join(_r, "pipeline.py")):
            if _r not in sys.path:
                sys.path.insert(0, _r)
            import pipeline as _m
            importlib.reload(_m)
            return _m, "pipeline.py: cargado desde " + _r
    log = ["KO: no se encontro pipeline.py. Rutas probadas:"]
    log += ["  - " + p for p in probadas]
    log.append("Solucion: doble clic en instalar.bat, o copia pipeline.py a la")
    log.append("carpeta del proyecto (junto a config_proyecto.xlsx), o define")
    log.append("la variable de entorno PIPELINE_HOME con su carpeta.")
    return None, "\n".join(log)


pipeline, _msg_carga = _cargar_pipeline()
if pipeline is None:
    OUT = _msg_carga
else:
    n_ok, n_ko, lineas = pipeline.autotest(verbose=False)
    OUT = "\n".join(lineas)


# =============================================================================
# UTILIDAD 4  ->  crear la config en EXCEL (la via comoda)
# Genera config_proyecto.xlsx en la carpeta del proyecto: se edita como
# una hoja normal (amarillo = obligatorio, desplegables donde aplica),
# se guarda, y el JSON se regenera SOLO al ejecutar cualquier fase.
# =============================================================================

import os
import sys
import importlib

# ---------------------------------------------------------------------------
# Localizador del modulo pipeline.py. Sin rutas escritas: prueba, en orden,
#   1) ya importable (instalado con instalar.bat en el Python de Dynamo)
#   2) variable de entorno PIPELINE_HOME (carpeta que contiene pipeline.py)
#   3) carpeta del proyecto: subiendo hasta 3 niveles desde el DWG activo
#      (el mismo criterio con el que se localiza config_proyecto.xlsx)
# Si ninguna funciona, OUT es un KO legible con las rutas probadas.
# ---------------------------------------------------------------------------
def _cargar_pipeline():
    probadas = []
    try:
        import pipeline as _m
        importlib.reload(_m)
        return _m, "pipeline.py: importado desde " + str(getattr(_m, "__file__", "?"))
    except ImportError:
        probadas.append("import directo (site-packages de Dynamo)")
    candidatas = []
    ph = os.environ.get("PIPELINE_HOME", "")
    if ph:
        candidatas.append(ph)
    try:
        import clr
        clr.AddReference("AcMgd")
        from Autodesk.AutoCAD.ApplicationServices import Application as _A
        _doc = _A.DocumentManager.MdiActiveDocument
        if _doc is not None:
            _c = os.path.dirname(os.path.abspath(str(_doc.Name)))
            for _ in range(3):
                candidatas.append(_c)
                _p = os.path.dirname(_c)
                if _p == _c:
                    break
                _c = _p
    except Exception as ex:
        probadas.append("DWG activo no disponible: " + str(ex)[:80])
    for _r in candidatas:
        probadas.append(_r)
        if _r and os.path.exists(os.path.join(_r, "pipeline.py")):
            if _r not in sys.path:
                sys.path.insert(0, _r)
            import pipeline as _m
            importlib.reload(_m)
            return _m, "pipeline.py: cargado desde " + _r
    log = ["KO: no se encontro pipeline.py. Rutas probadas:"]
    log += ["  - " + p for p in probadas]
    log.append("Solucion: doble clic en instalar.bat, o copia pipeline.py a la")
    log.append("carpeta del proyecto (junto a config_proyecto.xlsx), o define")
    log.append("la variable de entorno PIPELINE_HOME con su carpeta.")
    return None, "\n".join(log)


pipeline, _msg_carga = _cargar_pipeline()
if pipeline is None:
    OUT = _msg_carga
else:
    CARPETA_PROYECTO = r"C:\...\OneDrive\Proyectos\Estera"   # <- CAMBIAR
    NOMBRE_PROYECTO = "Estera"                               # <- CAMBIAR
    OUT = pipeline.crear_excel_plantilla(CARPETA_PROYECTO, NOMBRE_PROYECTO)
