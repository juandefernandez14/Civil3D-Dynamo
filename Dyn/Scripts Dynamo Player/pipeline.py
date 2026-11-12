# -*- coding: utf-8 -*-
# =============================================================================
# pipeline.py  -  v01  
#
# Modulo comun de CONFIGURACION + ESTADO para los scripts del pipeline
#
#   config_proyecto.json   una sola fuente de verdad de parametros
#   estado_pipeline.json   que produjo cada fase, firmas y aprobaciones
#   Logs/                  un fichero de log por ejecucion
#
# Entorno objetivo: Civil 3D 2024 / Dynamo 2.19 / CPython3 (pythonnet).
# El modulo NO importa ensamblados de AutoCAD 
#
# Uso desde Dynamo (2 nodos por script, ver cabecera_nodos_dynamo.py):
#   - Nodo CONFIG (al principio): pipeline.nodo_config(FASE)
#       valida prerrequisitos y devuelve los parametros en orden fijo.
#   - Nodo CIERRE (al final):     pipeline.nodo_cierre(...)
#       escribe estado + log e invalida las fases aguas abajo si aplico.
#
# Disciplina aplicada:
#   - escrituras atomicas (tmp con timestamp+PID -> os.replace) con
#     reintentos por bloqueos de OneDrive y copia .bak previa
#   - nunca "except: pass": todo fallo se registra con str(ex)[:120]
#   - los logs de los nodos terminan con veredicto claro OK/KO
# =============================================================================

import json
import os
import time
import hashlib
import shutil
import traceback

VERSION = "v25"  # v25: CIERRE detecta abortos limpios del motor ("Abortado.") y fuerza KO
VERSION_ESQUEMA = 1

NOMBRE_CONFIG = "config_proyecto.json"
NOMBRE_ESTADO = "estado_pipeline.json"
CARPETA_LOGS = "Logs"
MARCA_RELLENAR = "<RELLENAR>"

REINTENTOS_IO = 6
ESPERA_IO_S = 0.5
MAX_HISTORIAL = 100

# --------------------------------------------------------------------------- #
# Definicion del pipeline
# --------------------------------------------------------------------------- #

FASES = {
    "0": "Recorte MDT",
    "1NS": "Analisis pendientes NS (terreno)",
    "1EO": "Analisis pendientes EO (terreno)",
    "2": "Superficie de trackers",
    "3": "Correccion de pendientes",
    "1NST": "Analisis pendientes NS (trackers)",
    "1EOT": "Analisis pendientes EO (trackers)",
    "4": "Superficies de volumen",
    "5": "Zonas y manchas",
    "6": "Replanteo y Excel",
    "7": "Transversales",
}

# Cadena de dependencias directas. AJUSTAR aqui si la cadena real difiere
DEPENDENCIAS = {
    "0": [],
    "1NS": ["0"],
    "1EO": ["0"],
    "2": ["0"],
    "3": ["2"],
    "1NST": ["3"],
    "1EOT": ["3"],
    "4": ["3"],
    "5": ["4"],
    "6": ["5"],
    "7": ["5"],
}

# Orden FIJO en que nodo_config devuelve los parametros de cada fase.
# Este orden es el contrato de recableado en el .dyn: indice -> puerto.
# Las fases sin lista definida devuelven solo [ok, log, carpeta, firma].
PARAMS_FASE = {
    # Orden = orden REAL de los IN[] del nodo Python del grafo, saltando
    # el toggle de aplicar (que sigue siendo input manual por ejecucion).
    # Fase 0 segun 0_RecorteMDT_v07 (IN[4] 'Aplicar cambios' excluido).
    "0": [
        "superficie_mdt",
        "capa_contornos",
        "superficie_salida",
        "margen_extra_filtrado_m",
        "anclar_contorno_original",
        "paso_muestreo_borde_m",
        "offset_borde_m",
    ],
    # Fases 1NS/1EO segun 1_Slope_Analysis_Unificado (v1); analisis puro
    # sin toggle de aplicar. La ORIENTACION (IN[4]) NO va en config: es el
    # selector manual de variante (como APLICAR) y compone la subfase.
    "1NS": [
        "superficie_analisis",
        "capa_contorno",
        "capa_ejes",
        "tipo",
        "pendiente_max_pct",
        "pendiente_aviso_pct",
        "superficie_salida",
        "opcion_puntos",
        "pitch_min_m",
        "pitch_max_m",
        "iteraciones_subdivision",
    ],
    "1EO": [
        "superficie_analisis",
        "capa_contorno",
        "capa_ejes",
        "tipo",
        "pendiente_max_pct",
        "pendiente_aviso_pct",
        "superficie_salida",
        "opcion_puntos",
        "pitch_min_m",
        "pitch_max_m",
        "iteraciones_subdivision",
    ],
    # Fases 1NST/1EOT: misma plantilla de analisis, contra la superficie
    # de trackers, justo despues de la correccion de pendientes (fase 3).
    "1NST": [
        "superficie_analisis",
        "capa_contorno",
        "capa_ejes",
        "tipo",
        "pendiente_max_pct",
        "pendiente_aviso_pct",
        "superficie_salida",
        "opcion_puntos",
        "pitch_min_m",
        "pitch_max_m",
        "iteraciones_subdivision",
    ],
    "1EOT": [
        "superficie_analisis",
        "capa_contorno",
        "capa_ejes",
        "tipo",
        "pendiente_max_pct",
        "pendiente_aviso_pct",
        "superficie_salida",
        "opcion_puntos",
        "pitch_min_m",
        "pitch_max_m",
        "iteraciones_subdivision",
    ],
    # Fase 2 segun DIAG del grafo real 32 parametros
    # repartidos en 9 nodos destino; la Orientacion queda manual.
    "2": [
        "capa_contornos",
        "capa_trackers",
        "capa_ejes",
        "tol_agrupacion_m",
        "extension_extremos_m",
        "site",
        "estilo_alignment",
        "label_set",
        "add_curves",
        "superficie_mdt",
        "superficie_salida",
        "estilo_fl",
        "capa_perfiles",
        "estilo_perfil_trackers",
        "labelset_trackers",
        "prefijo_trackers",
        "estilo_perfil_tn",
        "labelset_tn",
        "prefijo_tn",
        "origin_x",
        "origin_y",
        "col_spacing",
        "row_spacing",
        "pv_prefix",
        "bandset",
        "estilo_pv",
        "patron_fl",
        "tolerancia_proyeccion_m",
        "estilo_proyeccion_fl",
        "suprimir_dialogos",
        "ruta_temp_lisp",
        "auto_ok_dialogos",
        "orientacion",
    ],
    # Fase 3 segun 3_CorreccionPendientes
    "3": [
        "modo",
        "patron_fl",
        "superficie_mdt",
        "superficie_trackers",
        "pendiente_ns_pct",
        "pendiente_eo_pct",
        "pitch_m",
        "margen_pitch_m",
        "escalon_max_m",
        "gap_contiguo_m",
        "tol_extremos_m",
        "tol_agrupacion_m",
        "etapa_correccion",
        "forzar",
        "max_pasadas_eo",
        "solape_min_m",
        "ratio_dt_objetivo",
        "rugosidad_m",
        "tol_rescate_m",
        "tol_ratio",
        "pendiente_hincas_pct",   # v22+: deflexion por hinca en % (IN[21])
        "deflexion_ala_pct",      # v23: deflexion acumulada por ala en % (IN[22])
    ],
    # Fase 4 segun 4_SuperficiesVolumen_MdT
    "4": [
        "superficie_trackers",
        "superficie_mdt",
        "rugosidad_mm",
        "prefijo_volumen",
        "capa_contornos",
    ],
    # Fase 5 segun 5_Superficies_Zonas_Manchas 
    "5": [
        "superficie_trackers",
        "superficie_mdt",
        "capa_contornos",
        "superficie_combinada",
        "offset_manchas_m",
        "filtro_manchas_pct",
        "pegar_mdt_base",
        "intentos_offset",
        "paso_offset_m",
    ],
    # Fase 6 segun 6_TablasExcel_v01; 'hojas_nombres' es OPCIONAL.
    "6": [
        "hojas_nombres",
        "filtro_dxf",
    ],
}

# Parametros que pueden quedar vacios sin bloquear la fase.
PARAMS_OPCIONALES = {
    "2": ("site", "estilo_proyeccion_fl"),
    "6": ("hojas_nombres",),
}


def _es_opcional(ruta_o_fase, clave=None):
    if clave is None:
        p = str(ruta_o_fase).split(".")
        if len(p) != 3 or p[0] != "fases":
            return False
        fase, clave = p[1], p[2]
    else:
        fase = str(ruta_o_fase)
    return clave in PARAMS_OPCIONALES.get(fase, ())

ESTADOS_VALIDOS_PREVIO = ("APLICADA", "APROBADA")

NOMBRE_CONFIG_XLSX = "config_proyecto.xlsx"

# Descripciones legibles para la hoja Excel. Se busca primero la ruta
# completa y despues el ultimo segmento de la clave.
AYUDA = {
    "proyecto": "Nombre del proyecto",
    "descripcion": "Descripcion libre",
    "exigir_aprobacion": "Puerta estricta: solo APROBADA desbloquea",
    "exigir_prerrequisitos":
        "Puerta de prerrequisitos: exigir fase previa APLICADA",
    "scale_factor": "Factor de escala UTM (ETRS89/30N)",
    "epsg": "Codigo EPSG del proyecto",
    "cierre_virtual_max_m": "Cierre virtual maximo de polilineas (m)",
    "contornos": "Capa de contornos",
    "trackers": "Capa / DWG de trackers",
    "ejes": "Capa de ejes",
    "mdt": "Superficie / DWG del MDT",
    "mdt_recortado": "Superficie MDT recortada",
    "volumenes": "DWG de volumenes",
    "analisis": "DWG del analisis de pendientes",
    "dwg": "DWG de la fase (nombre o clave de 'dwgs')",
    "superficie_mdt": "Superficie MDT de entrada",
    "superficie_salida": "Superficie de salida",
    "superficie_analisis": "Superficie a analizar",
    "superficie_trackers": "Superficie de trackers",
    "capa_contornos": "Capa de contornos",
    "capa_contorno": "Capa de contorno",
    "capa_trackers": "Capa de trackers",
    "capa_ejes": "Capa de ejes",
    "margen_extra_filtrado_m": "Margen extra de filtrado (m)",
    "anclar_contorno_original": "Anclar contorno original (S/N)",
    "paso_muestreo_borde_m": "Paso de muestreo del borde (m)",
    "offset_borde_m": "Offset del borde hacia fuera (m)",
    "tipo": "Tipo de elemento (Trackers/Mesas)",
    "pendiente_max_pct": "Pendiente maxima (%)",
    "pendiente_aviso_pct": "Pendiente de aviso (%)",
    "opcion_puntos": "Opcion de puntos",
    "pitch_min_m": "Pitch minimo (m)",
    "pitch_max_m": "Pitch maximo (m)",
    "iteraciones_subdivision": "Iteraciones de subdivision",
    "estilo_fl": "Estilo de feature line",
    "col_tol_m": "Tolerancia de columna (m)",
    "extension_ejes_m": "Extension de ejes (m)",
    "patron_fl": "Patron de nombre de FL",
    "tolerancia_proyeccion_m": "Tolerancia de proyeccion (m)",
    "modo": "Modo (NS/EO)",
    "pendiente_ns_pct": "Limite de pendiente NS (%)",
    "pendiente_eo_pct": "Limite de pendiente EO (%)",
    "pendiente_hincas_pct": "Deflexion por hinca (%)",
    "deflexion_ala_pct": "Deflexion acumulada por ala (%)",
    "pitch_m": "Pitch nominal (m)",
    "margen_pitch_m": "Margen de pitch (m)",
    "escalon_max_m": "Escalon maximo (m)",
    "gap_contiguo_m": "GAP de continuidad (m)",
    "tol_extremos_m": "Tolerancia de extremos (m)",
    "tol_agrupacion_m": "Tolerancia de agrupacion (m)",
    "etapa_correccion": "Etapa (LONG/LONG+EO)",
    "forzar": "FORZAR resolucion",
    "max_pasadas_eo": "Maximo de pasadas EO",
    "solape_min_m": "Solape minimo (m)",
    "ratio_dt_objetivo": "Ratio D/T objetivo",
    "rugosidad_m": "Rugosidad (m)",
    "tol_rescate_m": "Tolerancia de rescate (m)",
    "tol_ratio": "Tolerancia del ratio",
    "analisis_ns": "DWG analisis terreno NS",
    "analisis_eo": "DWG analisis terreno EO",
    "analisis_trackers_ns": "DWG analisis vs trackers NS",
    "analisis_trackers_eo": "DWG analisis vs trackers EO",
    "superficie_combinada": "Superficie combinada",
    "offset_manchas_m": "Offset de manchas (m)",
    "filtro_manchas_pct": "Filtro de manchas (% area media)",
    "pegar_mdt_base": "Pegar MDT base en combinada (S/N)",
    "intentos_offset": "Intentos de offset (0=off)",
    "paso_offset_m": "Paso de offset (m)",
    "rugosidad_mm": "Rugosidad +- (mm)",
    "prefijo_volumen": "Prefijo del nombre de volumen",
    "hojas_nombres": "Nombres de hojas (coma, opcional)",
    "filtro_dxf": "Filtro DXF de tablas",
    "extension_extremos_m": "Extension de extremos de eje (m)",
    "site": "Site de alignments (vacio = None)",
    "estilo_alignment": "Estilo de alignment",
    "label_set": "Label set de alignments",
    "add_curves": "Anyadir curvas al alignment",
    "capa_perfiles": "Capa de los perfiles",
    "estilo_perfil_trackers": "Estilo perfil Trackers",
    "labelset_trackers": "LabelSet perfil Trackers",
    "prefijo_trackers": "Prefijo perfiles Trackers",
    "estilo_perfil_tn": "Estilo perfil TN",
    "labelset_tn": "LabelSet perfil TN",
    "prefijo_tn": "Prefijo perfiles TN",
    "origin_x": "Origen X de ProfileViews (UTM)",
    "origin_y": "Origen Y de ProfileViews (UTM)",
    "col_spacing": "Separacion columnas PV (m)",
    "row_spacing": "Separacion filas PV (m)",
    "pv_prefix": "Prefijo de ProfileViews",
    "bandset": "Band set de ProfileViews",
    "estilo_pv": "Estilo de ProfileView",
    "estilo_proyeccion_fl": "Estilo proyeccion FL (vacio = ref)",
    "suprimir_dialogos": "Suprimir dialogos (best-effort)",
    "ruta_temp_lisp": "Fichero temporal de intercambio LISP",
    "auto_ok_dialogos": "Auto-OK de dialogos (PowerShell)",
    "orientacion": "Orientacion de los ejes (NS/EO)",
}

# Celdas enlazadas de la hoja Excel: el destino se rellena por formula
# desde el origen (una unica fuente de verdad, normalmente Generales).
ENLACES = {
    "fases.0.superficie_mdt": "superficies.mdt",
    "fases.0.superficie_salida": "superficies.mdt_recortado",
    "fases.0.capa_contornos": "capas.contornos",
    "fases.1NS.superficie_analisis": "superficies.mdt_recortado",
    "fases.1NS.capa_contorno": "capas.contornos",
    "fases.1NS.capa_ejes": "capas.ejes",
    "fases.1EO.superficie_analisis": "superficies.mdt_recortado",
    "fases.1EO.capa_contorno": "capas.contornos",
    "fases.1EO.capa_ejes": "capas.ejes",
    "fases.1NST.superficie_analisis": "superficies.trackers",
    "fases.1NST.capa_contorno": "capas.contornos",
    "fases.1NST.capa_ejes": "capas.ejes",
    "fases.1EOT.superficie_analisis": "superficies.trackers",
    "fases.1EOT.capa_contorno": "capas.contornos",
    "fases.1EOT.capa_ejes": "capas.ejes",
    "fases.2.superficie_mdt": "superficies.mdt_recortado",
    "fases.2.capa_contornos": "capas.contornos",
    "fases.2.capa_trackers": "capas.trackers",
    "fases.2.superficie_salida": "superficies.trackers",
    "fases.2.capa_ejes": "capas.ejes",
    "fases.2.orientacion": "fases.3.modo",
    "fases.3.superficie_mdt": "superficies.mdt_recortado",
    "fases.3.superficie_trackers": "superficies.trackers",
    "fases.3.patron_fl": "fases.2.patron_fl",
    "fases.4.superficie_trackers": "superficies.trackers",
    "fases.4.superficie_mdt": "superficies.mdt_recortado",
    "fases.4.capa_contornos": "capas.contornos",
    "fases.5.superficie_trackers": "superficies.trackers",
    "fases.5.superficie_mdt": "superficies.mdt_recortado",
    "fases.5.capa_contornos": "capas.contornos",
}

# Nota funcional brevisima por casilla (busca ruta completa y despues
# ultimo segmento). Se compone con los marcadores (obligatorio, etc.).
NOTAS = {
    "proyecto": "nombre que aparece en logs y estado",
    "descripcion": "texto libre del proyecto",
    "exigir_aprobacion":
        "TRUE = cada fase exige APROBAR la anterior, no basta aplicar",
    "exigir_prerrequisitos":
        "TRUE = bloquear si la fase previa no esta APLICADA; FALSE (por "
        "defecto) = solo avisar, no bloquea",
    "scale_factor": "factor de trabajo de Dynamo para UTM",
    "epsg": "sistema de coordenadas del proyecto",
    "cierre_virtual_max_m":
        "hueco maximo que se cierra virtualmente en contornos",
    "capas.contornos": "capa de los contornos de zonas",
    "capas.trackers": "capa de las lineas de trackers (rotura)",
    "capas.ejes": "capa donde se crean los ejes/alignments",
    "superficies.mdt": "MDT original: entrada de la fase 0",
    "superficies.mdt_recortado": "superficie que CREA la fase 0",
    "superficies.trackers": "superficie que CREA la fase 2",
    "dwg": "DWG que debe estar activo al ejecutar (guardarrail)",
    "dwgs.mdt": "fichero DWG de la fase 0",
    "dwgs.trackers": "fichero DWG de las fases 2 y 3",
    "dwgs.volumenes": "fichero DWG de las fases 4, 5 y 6",
    "dwgs.analisis_ns": "fichero DWG del analisis terreno NS",
    "dwgs.analisis_eo": "fichero DWG del analisis terreno EO",
    "dwgs.analisis_trackers_ns": "DWG del analisis vs trackers NS",
    "dwgs.analisis_trackers_eo": "DWG del analisis vs trackers EO",
    "fases.0.superficie_mdt": "MDT a recortar",
    "fases.0.capa_contornos": "contornos que definen el recorte",
    "fases.0.superficie_salida": "nombre de la superficie recortada",
    "margen_extra_filtrado_m":
        "margen extra del filtro de vertices alrededor del contorno",
    "anclar_contorno_original":
        "S = clava el anillo del contorno con su cota real",
    "paso_muestreo_borde_m": "cada cuantos metros se ancla el borde",
    "offset_borde_m": "desfase del contorno hacia fuera para cortar",
    "superficie_analisis": "superficie cuyas pendientes se analizan",
    "capa_contorno": "contorno que delimita el analisis",
    "fases.1NS.capa_ejes": "lineas de rotura usadas en el analisis",
    "fases.1EO.capa_ejes": "lineas de rotura usadas en el analisis",
    "fases.1NST.capa_ejes": "lineas de rotura usadas en el analisis",
    "fases.1EOT.capa_ejes": "lineas de rotura usadas en el analisis",
    "tipo": "geometria del elemento analizado",
    "pendiente_max_pct": "umbral rojo: pendiente maxima (%)",
    "pendiente_aviso_pct": "umbral amarillo de aviso (%)",
    "fases.1NS.superficie_salida": "superficie de analisis creada",
    "fases.1EO.superficie_salida": "superficie de analisis creada",
    "fases.1NST.superficie_salida": "superficie de analisis creada",
    "fases.1EOT.superficie_salida": "superficie de analisis creada",
    "opcion_puntos": "estrategia de puntos del analisis",
    "pitch_min_m": "pitch minimo considerado (m)",
    "pitch_max_m": "pitch maximo considerado (m)",
    "iteraciones_subdivision": "refinado: subdivisiones del muestreo",
    "fases.2.capa_ejes": "capa destino de los alignments",
    "tol_agrupacion_m":
        "distancia maxima para agrupar trackers en un mismo eje",
    "fases.3.tol_agrupacion_m": "agrupacion de columnas del barrido",
    "extension_extremos_m": "prolongacion de los ejes en extremos (m)",
    "site": "site de los alignments (vacio = ninguno)",
    "estilo_alignment": "estilo C3D del alignment",
    "label_set": "label set de los alignments",
    "add_curves": "TRUE anyade curvas al alignment",
    "fases.2.superficie_mdt": "MDT (shortcut) para los perfiles TN",
    "fases.2.superficie_salida": "superficie de trackers creada",
    "estilo_fl": "estilo de las feature lines de trackers",
    "capa_perfiles": "capa de los perfiles creados",
    "estilo_perfil_trackers": "estilo del perfil de trackers",
    "labelset_trackers": "etiquetas del perfil de trackers",
    "prefijo_trackers": "prefijo del nombre del perfil trackers",
    "estilo_perfil_tn": "estilo del perfil de terreno natural",
    "labelset_tn": "etiquetas del perfil de terreno natural",
    "prefijo_tn": "prefijo del nombre del perfil TN",
    "origin_x": "esquina X de la reticula de ProfileViews (UTM)",
    "origin_y": "esquina Y de la reticula de ProfileViews (UTM)",
    "col_spacing": "separacion entre columnas de PVs (m)",
    "row_spacing": "separacion entre filas de PVs (m)",
    "pv_prefix": "prefijo del nombre de cada ProfileView",
    "bandset": "band set aplicado a los ProfileViews",
    "estilo_pv": "estilo del ProfileView",
    "fases.2.patron_fl": "patron de nombres de FL a proyectar",
    "tolerancia_proyeccion_m":
        "distancia maxima FL-eje para emparejar en la proyeccion",
    "estilo_proyeccion_fl": "estilo de la proyeccion (vacio = ref)",
    "suprimir_dialogos": "intenta silenciar dialogos de proyeccion",
    "ruta_temp_lisp": "fichero puente Python-LISP de la proyeccion",
    "auto_ok_dialogos": "PowerShell pulsa OK en dialogos automaticos",
    "fases.2.orientacion": "hereda del modo de la fase 3 (selector)",
    "modo": "eje longitudinal de la correccion",
    "fases.3.patron_fl": "patron de las FL de trackers a corregir",
    "fases.3.superficie_mdt": "terreno de referencia (MDT recortado)",
    "fases.3.superficie_trackers": "superficie de trackers a corregir",
    "pendiente_ns_pct": "limite de pendiente admisible N-S (%)",
    "pendiente_eo_pct": "limite de pendiente admisible E-O (%)",
    "pendiente_hincas_pct":
        "trackers FLEXIBLES: quiebro maximo del tubo en cada hinca, como "
        "cambio de pendiente en % (0,75 grados = 1,31). Solo actua con "
        "vertices intermedios; con 2 vertices NO se utiliza",
    "deflexion_ala_pct":
        "trackers FLEXIBLES: suma maxima de |quiebros| desde la hinca "
        "motora (central) a cada extremo, en % (8 grados = 13,96). La "
        "motora no computa en las alas",
    "pitch_m": "pitch nominal entre trackers (m)",
    "margen_pitch_m": "tolerancia del pitch (+-m)",
    "escalon_max_m": "escalon maximo entre trackers contiguos (m)",
    "gap_contiguo_m": "separacion maxima para considerar contiguos",
    "tol_extremos_m": "movimiento maximo en extremos de eje (m)",
    "etapa_correccion": "LONG solo longitudinal; +EO barre transversal",
    "forzar": "TRUE agota escenarios hasta resolver o demostrar",
    "max_pasadas_eo": "tope de pasadas del barrido E-O",
    "solape_min_m": "solape minimo entre trackers enfrentados (m)",
    "ratio_dt_objetivo": "reparto objetivo desmonte/terraplen",
    "rugosidad_m": "holgura de rugosidad admitida (m)",
    "tol_rescate_m": "margen extra del rescate PEINE (m)",
    "tol_ratio": "tolerancia sobre el ratio objetivo",
    "fases.4.superficie_trackers": "superficie corregida a medir",
    "fases.4.superficie_mdt": "terreno contra el que se mide volumen",
    "rugosidad_mm": "banda +-mm ignorada como rugosidad",
    "prefijo_volumen": "prefijo de cada superficie de volumen",
    "fases.4.capa_contornos": "contornos que delimitan cada zona",
    "fases.5.superficie_trackers": "superficie corregida de entrada",
    "fases.5.superficie_mdt": "terreno base del MDT modificado",
    "fases.5.capa_contornos": "contornos que delimitan cada zona",
    "superficie_combinada": "nombre del MDT modificado resultante",
    "offset_manchas_m": "offset interior aplicado a las manchas",
    "filtro_manchas_pct": "descarta manchas < este % del area media",
    "pegar_mdt_base": "S pega el MDT base en la combinada",
    "intentos_offset": "reintentos del offset antiloteria (0=off)",
    "paso_offset_m": "incremento del offset por reintento (m)",
    "hojas_nombres": "hojas destino por comas (vacio = todas)",
    "filtro_dxf": "tipos de tabla CAD que se capturan",
}


def _copiar(estilo):
    import copy
    return copy.copy(estilo)


def _nota_funcional(ruta_k):
    if ruta_k in NOTAS:
        return NOTAS[ruta_k]
    return NOTAS.get(ruta_k.split(".")[-1])


def _nota(ruta_k, marcador=None):
    partes = [p for p in (marcador, _nota_funcional(ruta_k)) if p]
    return " - ".join(partes) if partes else None


# Celdas fijas: llevan valor de serie y no deben cambiarse.
NOTAS_FIJAS = {
    "fases.2.estilo_fl": "fijo: no cambiar",
    "fases.2.ruta_temp_lisp": "fijo salvo cambio de maquina",
}

# Desplegables por ultimo segmento de la clave (validacion en la hoja).
DESPLEGABLES = {
    "anclar_contorno_original": '"S,N"',
    "tipo": '"Trackers,Mesas"',
    "modo": '"NS,EO"',
    "etapa_correccion": '"LONG,LONG+EO"',
    "forzar": '"TRUE,FALSE"',
    "exigir_aprobacion": '"TRUE,FALSE"',
    "exigir_prerrequisitos": '"TRUE,FALSE"',
    "pegar_mdt_base": '"S,N"',
    "add_curves": '"TRUE,FALSE"',
    "suprimir_dialogos": '"TRUE,FALSE"',
    "auto_ok_dialogos": '"TRUE,FALSE"',
}

SEP = "=" * 62
SUB = "-" * 62


# --------------------------------------------------------------------------- #
# Utilidades basicas
# --------------------------------------------------------------------------- #

def _ahora():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _usuario():
    u = os.environ.get("USERNAME") or os.environ.get("USER")
    if u:
        return u
    try:
        import getpass
        return getpass.getuser()
    except Exception as ex:
        return "desconocido(" + str(ex)[:40] + ")"


def _equipo():
    return (os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME")
            or "desconocido")


def _dwg_activo():
    """Intenta obtener la ruta del DWG activo via API de AutoCAD.
    Devuelve (ruta_o_None, aviso). Offline devuelve (None, motivo)."""
    try:
        import clr
        clr.AddReference("AcMgd")
        from Autodesk.AutoCAD.ApplicationServices import (
            Application as _AcadApp)
        doc = _AcadApp.DocumentManager.MdiActiveDocument
        if doc is None:
            return None, "sin documento activo en AutoCAD"
        return str(doc.Name), ""
    except Exception as ex:
        return None, "sin AutoCAD (modo offline): " + str(ex)[:120]


def _leer_json(ruta):
    """Lee un JSON con reintentos (OneDrive) y rescate desde .bak.
    Devuelve (datos_o_None, aviso)."""
    aviso = ""
    for intento in range(REINTENTOS_IO):
        try:
            f = open(ruta, "r", encoding="utf-8")
            try:
                return json.load(f), aviso
            finally:
                f.close()
        except FileNotFoundError:
            return None, "no existe: " + ruta
        except ValueError as ex:
            aviso = "JSON corrupto (" + str(ex)[:80] + "), pruebo .bak"
            ruta_bak = ruta + ".bak"
            if os.path.exists(ruta_bak):
                try:
                    fb = open(ruta_bak, "r", encoding="utf-8")
                    try:
                        datos = json.load(fb)
                    finally:
                        fb.close()
                    return datos, aviso + " -> rescatado de .bak"
                except Exception as ex2:
                    return None, aviso + " -> .bak tambien KO: " + str(ex2)[:80]
            return None, aviso + " -> no hay .bak"
        except (PermissionError, OSError) as ex:
            aviso = ("bloqueo de lectura intento {}/{}: {}"
                     .format(intento + 1, REINTENTOS_IO, str(ex)[:80]))
            time.sleep(ESPERA_IO_S)
    return None, aviso


def _escribir_json_atomico(ruta, datos):
    """Escritura atomica: tmp con timestamp+PID -> os.replace, con copia
    .bak del fichero previo y reintentos por bloqueos de OneDrive.
    Devuelve (ok, aviso)."""
    tmp = "{}.tmp_{}_{}".format(ruta, int(time.time()), os.getpid())
    try:
        f = open(tmp, "w", encoding="utf-8")
        try:
            json.dump(datos, f, indent=2, ensure_ascii=True, sort_keys=False)
        finally:
            f.close()
    except Exception as ex:
        return False, "no pude escribir tmp: " + str(ex)[:120]
    if os.path.exists(ruta):
        try:
            shutil.copyfile(ruta, ruta + ".bak")
        except Exception as ex:
            # No es bloqueante, pero queda registrado en el aviso.
            aviso_bak = " (aviso: .bak no actualizado: " + str(ex)[:80] + ")"
        else:
            aviso_bak = ""
    else:
        aviso_bak = ""
    for intento in range(REINTENTOS_IO):
        try:
            os.replace(tmp, ruta)
            return True, "escrito" + aviso_bak
        except (PermissionError, OSError) as ex:
            ultimo = str(ex)[:80]
            time.sleep(ESPERA_IO_S)
    try:
        os.remove(tmp)
    except Exception as ex:
        ultimo = ultimo + " / tmp sin borrar: " + str(ex)[:60]
    return False, ("bloqueado tras {} intentos (OneDrive?): {}"
                   .format(REINTENTOS_IO, ultimo))


def _firma_config(cfg, fase):
    """Hash corto y estable de (parametros_comunes + fases[fase])."""
    subconjunto = {
        "comunes": cfg.get("parametros_comunes", {}),
        "fase": cfg.get("fases", {}).get(str(fase), {}),
    }
    texto = json.dumps(subconjunto, sort_keys=True, ensure_ascii=True)
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:8]


def _descendientes(fase):
    """Cierre transitivo de las fases que dependen (directa o
    indirectamente) de 'fase'."""
    fase = str(fase)
    resultado = set()
    cambio = True
    while cambio:
        cambio = False
        for f, reqs in DEPENDENCIAS.items():
            if f in resultado:
                continue
            for r in reqs:
                if r == fase or r in resultado:
                    resultado.add(f)
                    cambio = True
                    break
    return sorted(resultado)


# --------------------------------------------------------------------------- #
# Localizacion del proyecto (carpeta con config_proyecto.json)
# --------------------------------------------------------------------------- #

def localizar_proyecto(dwg_path=None):
    """Busca config_proyecto.json subiendo niveles desde la carpeta del
    DWG (activo o indicado). Devuelve (carpeta_o_None, log_lineas)."""
    lineas = []
    aviso_dwg = ""
    if dwg_path is None:
        dwg_path, aviso_dwg = _dwg_activo()
        if aviso_dwg:
            lineas.append("AVISO: " + aviso_dwg)
    if not dwg_path:
        lineas.append("KO: sin ruta de DWG para localizar el proyecto")
        return None, lineas
    lineas.append("DWG: " + str(dwg_path))
    carpeta = os.path.dirname(os.path.abspath(str(dwg_path)))
    niveles = 3
    for i in range(niveles):
        hay_json = os.path.exists(os.path.join(carpeta, NOMBRE_CONFIG))
        hay_xlsx = os.path.exists(os.path.join(carpeta, NOMBRE_CONFIG_XLSX))
        if hay_json or hay_xlsx:
            via = "" if hay_json else " (via Excel: el JSON se genera ahora)"
            lineas.append("config encontrada en: " + carpeta + via)
            return carpeta, lineas
        lineas.append("  no esta en: " + carpeta)
        padre = os.path.dirname(carpeta)
        if padre == carpeta:
            break
        carpeta = padre
    lineas.append("KO: no se encontro {} ni {} en {} niveles"
                  .format(NOMBRE_CONFIG, NOMBRE_CONFIG_XLSX, niveles))
    lineas.append("    (usa crear_config_plantilla() para generarla)")
    return None, lineas


def leer_config(carpeta):
    """Lee la config del proyecto. Si existe config_proyecto.xlsx y es
    mas reciente que el JSON (o el JSON no existe), regenera el JSON
    desde la hoja automaticamente: editar Excel, guardar, y ejecutar."""
    ruta_json = os.path.join(carpeta, NOMBRE_CONFIG)
    ruta_xlsx = os.path.join(carpeta, NOMBRE_CONFIG_XLSX)
    aviso_x = ""
    if os.path.exists(ruta_xlsx):
        mt_x = os.path.getmtime(ruta_xlsx)
        mt_j = (os.path.getmtime(ruta_json)
                if os.path.exists(ruta_json) else -1.0)
        if mt_x > mt_j + 1.0:
            marca = time.strftime("%Y-%m-%d %H:%M", time.localtime(mt_x))
            res_x = excel_a_config(carpeta)
            if res_x[0]:
                aviso_x = ("config regenerada desde Excel (guardado "
                           + marca + ")")
            else:
                aviso_x = ("AVISO: Excel mas reciente (" + marca
                           + ") pero no pude regenerar: " + res_x[1])
    datos, aviso = _leer_json(ruta_json)
    if aviso_x:
        aviso = aviso_x + ("; " + aviso if aviso else "")
    return datos, aviso


def _estado_vacio(cfg):
    return {
        "version_esquema": VERSION_ESQUEMA,
        "proyecto": (cfg or {}).get("proyecto", ""),
        "fases": {},
        "historial": [],
    }


def leer_estado(carpeta, cfg=None):
    ruta = os.path.join(carpeta, NOMBRE_ESTADO)
    if not os.path.exists(ruta):
        return _estado_vacio(cfg), "estado nuevo (aun no existia)"
    datos, aviso = _leer_json(ruta)
    if datos is None:
        return _estado_vacio(cfg), "KO leyendo estado: " + aviso
    return datos, aviso


# --------------------------------------------------------------------------- #
# NODO A: configuracion + prerrequisitos  (solo lectura)
# --------------------------------------------------------------------------- #

def nodo_config(fase, dwg_path=None):
    """Para el primer nodo del script. Devuelve una lista:
        [ok, log, carpeta_proyecto, firma, p1, p2, ... pn]
    con los parametros en el orden de PARAMS_FASE[fase].
    Si ok es False los parametros van a None y el log explica por que."""
    fase = str(fase)
    t0 = time.perf_counter()
    L = []
    ok = True

    L.append(SEP)
    L.append("PIPELINE {}  -  NODO CONFIG  -  FASE {} ({})"
             .format(VERSION, fase, FASES.get(fase, "?")))
    L.append(SEP)
    L.append("{:<14}{}".format("fecha:", _ahora()))
    L.append("{:<14}{} @ {}".format("usuario:", _usuario(), _equipo()))
    if fase not in FASES:
        ok = False
        L.append("KO: fase desconocida {!r}; validas: {}".format(
            fase, ", ".join(sorted(FASES))))

    if dwg_path is None:
        dwg_path, _aviso_dwg = _dwg_activo()
    carpeta, lin_loc = localizar_proyecto(dwg_path)
    L.extend(lin_loc)
    claves = PARAMS_FASE.get(fase, [])
    if carpeta is None:
        L.append(SEP)
        L.append("VEREDICTO: KO (proyecto no localizado)")
        return [False, "\n".join(L), "", ""] + [None] * len(claves)

    cfg, aviso_cfg = leer_config(carpeta)
    if aviso_cfg:
        L.append("AVISO config: " + aviso_cfg)
    if cfg is None:
        L.append("VEREDICTO: KO (config ilegible)")
        return [False, "\n".join(L), carpeta, ""] + [None] * len(claves)
    if cfg.get("version_esquema") != VERSION_ESQUEMA:
        L.append("AVISO: version_esquema={} y este modulo espera {}"
                 .format(cfg.get("version_esquema"), VERSION_ESQUEMA))
    L.append("{:<14}{}".format("proyecto:", cfg.get("proyecto", "?")))
    firma = _firma_config(cfg, fase)
    L.append("{:<14}{}".format("firma config:", firma))

    # ---- guardarrail: DWG declarado para la fase (opcional) --------------
    dwg_cfg = cfg.get("fases", {}).get(fase, {}).get("dwg")
    if dwg_cfg:
        esperado = cfg.get("dwgs", {}).get(dwg_cfg, dwg_cfg)
        nombre_esp = os.path.splitext(
            os.path.basename(str(esperado)))[0].lower()
        nombre_act = os.path.splitext(
            os.path.basename(str(dwg_path or "")))[0].lower()
        if esperado == MARCA_RELLENAR or not nombre_esp:
            L.append("AVISO: 'dwg' de la fase apunta a un valor sin "
                     "rellenar en config")
        elif nombre_act != nombre_esp:
            ok = False
            L.append("KO: esta fase corresponde al DWG '{}' y el activo "
                     "es '{}'".format(nombre_esp, nombre_act or "?"))
        else:
            L.append("{:<14}{} (coincide)".format("dwg fase:", nombre_esp))

    estado, aviso_est = leer_estado(carpeta, cfg)
    if aviso_est:
        L.append("estado: " + aviso_est)

    # ---- prerrequisitos ---------------------------------------------------
    # v24: la puerta de prerrequisitos es OPCIONAL. Por defecto NO bloquea:
    # los prerrequisitos no cumplidos se informan como AVISO. Se bloquea
    # solo si opciones.exigir_prerrequisitos = True (o exigir_aprobacion,
    # que implica la puerta estricta completa).
    exigir_aprob = bool(cfg.get("opciones", {}).get("exigir_aprobacion",
                                                    False))
    exigir_prereq = exigir_aprob or bool(
        cfg.get("opciones", {}).get("exigir_prerrequisitos", False))
    reqs = DEPENDENCIAS.get(fase, [])
    L.append(SUB)
    if not reqs:
        L.append("prerrequisitos: ninguno")
    else:
        L.append("prerrequisitos:")
    for r in reqs:
        fr = estado.get("fases", {}).get(r, {})
        est_r = fr.get("estado", "SIN_EJECUTAR")
        ue = fr.get("ultima_ejecucion", {}) or {}
        detalle = "{} ({} por {})".format(
            est_r, ue.get("timestamp", "-"), ue.get("usuario", "-"))
        if exigir_aprob:
            cumple = est_r == "APROBADA"
        else:
            cumple = est_r in ESTADOS_VALIDOS_PREVIO
        if cumple:
            marca = "OK "
        elif exigir_prereq:
            marca = "KO "
        else:
            marca = "AVISO "
        L.append("  {}fase {} ({}): {}".format(
            marca, r, FASES.get(r, "?"), detalle))
        if not cumple:
            if exigir_prereq:
                ok = False
            else:
                L.append("      (la puerta de prerrequisitos esta "
                         "desactivada: no bloquea; activala con "
                         "opciones.exigir_prerrequisitos)")
            if est_r == "DESACTUALIZADA":
                inval = fr.get("invalidada_por", {})
                L.append("      invalidada por fase {} el {}".format(
                    inval.get("fase", "?"), inval.get("timestamp", "?")))
        else:
            firma_r_actual = _firma_config(cfg, r)
            firma_r_usada = ue.get("firma_config", "")
            if firma_r_usada and firma_r_usada != firma_r_actual:
                L.append("      ADVERTENCIA: la config de la fase {} cambio "
                         "tras su ejecucion ({} -> {})"
                         .format(r, firma_r_usada, firma_r_actual))

    # ---- parametros -------------------------------------------------------
    comunes = cfg.get("parametros_comunes", {})
    propios = cfg.get("fases", {}).get(fase, {})
    valores = []
    faltan = []
    L.append(SUB)
    if claves:
        L.append("parametros (orden de recableado):")
    else:
        L.append("parametros: fase sin PARAMS_FASE definido todavia")
    for i, clave in enumerate(claves):
        if clave in propios:
            v = propios[clave]
        elif clave in comunes:
            v = comunes[clave]
        else:
            v = None
        if v is None or v == MARCA_RELLENAR or v == "":
            if _es_opcional(fase, clave):
                valores.append("")
                L.append("  [{:>2}] {:<26}(opcional, vacio)".format(
                    i + 4, clave))
            else:
                faltan.append(clave)
                valores.append(None)
                L.append("  [{:>2}] {:<26}KO (falta o {})".format(
                    i + 4, clave, MARCA_RELLENAR))
        else:
            valores.append(v)
            L.append("  [{:>2}] {:<26}{}".format(i + 4, clave, v))
    if faltan:
        ok = False
        L.append("KO: faltan {} parametros en config: {}"
                 .format(len(faltan), ", ".join(faltan)))

    L.append(SUB)
    L.append("{:<27}{:>7.2f} s".format("nodo_config", time.perf_counter() - t0))
    L.append("VEREDICTO: {}".format("OK" if ok else "KO"))
    L.append(SEP)
    return [ok, "\n".join(L), carpeta, firma] + valores


# --------------------------------------------------------------------------- #
# NODO B: cierre de fase  (escribe estado + log)
# --------------------------------------------------------------------------- #

def _detectar_error_en_log(log_script):
    """Devuelve una etiqueta corta si el log del script lleva firma de
    fallo (traceback de Python, ERROR:/KO: al principio de linea, o el
    marcador de auditoria Z), o '' si no. Se mira solo el texto: no
    depende de como este cableado el nodo."""
    txt = str(log_script or "")
    if not txt:
        return ""
    if "Traceback (most recent call last)" in txt:
        return "traceback"
    for linea in txt.splitlines():
        l = linea.strip()
        if l.startswith("!!!!!! AUDITORIA Z"):
            return "auditoria Z"
        if l.startswith("ERROR:") or l.startswith("ERROR general:"):
            return "linea ERROR"
        if l.startswith("Exception:"):
            return "excepcion"
        # v25: abortos limpios del motor ("!!!! Falta X. Abortado.").
        # OJO: el banner de mejor-esfuerzo de FORZAR ("IMPOSIBLE CUMPLIR")
        # NO es un aborto: la corrida completo y aplico; no debe forzar KO.
        if l.endswith("Abortado.") or l.startswith("!!!! "):
            return "aborto del script"
    return ""


def nodo_cierre(fase, log_script, resultados=None, aplicado=False, ok=True,
                auditoria_z="N/A", duracion_s=None, dwg_path=None):
    """Para el ultimo nodo del script (tras la barrera de sincronizacion).
    Escribe estado_pipeline.json y el log en Logs/. Devuelve:
        [ok_cierre, log_completo]
    donde log_completo = log_script + bloque de cierre (para el Watch)."""
    fase = str(fase)
    t0 = time.perf_counter()
    C = []
    ok_cierre = True

    C.append(SEP)
    C.append("PIPELINE {}  -  NODO CIERRE  -  FASE {} ({})"
             .format(VERSION, fase, FASES.get(fase, "?")))
    C.append(SEP)

    carpeta, lin_loc = localizar_proyecto(dwg_path)
    C.extend(lin_loc)
    if carpeta is None:
        C.append("VEREDICTO CIERRE: KO (estado NO escrito)")
        return [False, str(log_script or "") + "\n" + "\n".join(C)]

    cfg, aviso_cfg = leer_config(carpeta)
    if cfg is None:
        C.append("KO config: " + aviso_cfg)
        C.append("VEREDICTO CIERRE: KO (estado NO escrito)")
        return [False, str(log_script or "") + "\n" + "\n".join(C)]

    estado, aviso_est = leer_estado(carpeta, cfg)
    if aviso_est:
        C.append("estado: " + aviso_est)

    if resultados is None or resultados == "":
        resultados = {}
    elif isinstance(resultados, str):
        try:
            resultados = json.loads(resultados)
        except ValueError as ex:
            C.append("AVISO: resultados como texto no-JSON ({}), lo guardo "
                     "tal cual".format(str(ex)[:60]))
            resultados = {"texto": resultados[:500]}

    # v21: red de seguridad. En modo sombra el input 'ok' del nodo CIERRE
    # suele venir de una constante True, asi que si el script ha
    # reventado (traceback / ERROR en el log) el estado quedaria APLICADA
    # con un falso OK. Se detecta la firma de error en el propio log y se
    # fuerza KO, dejandolo escrito.
    firma_error = _detectar_error_en_log(log_script)
    if ok and firma_error:
        ok = False
        C.append("KO detectado en el log del script ({}); el veredicto "
                 "del script se fuerza a KO aunque el input 'ok' fuera "
                 "True".format(firma_error))

    if not ok:
        nuevo_estado = "KO"
    elif aplicado:
        nuevo_estado = "APLICADA"
    else:
        nuevo_estado = "EJECUTADA"

    ts = _ahora()
    entrada = {
        "timestamp": ts,
        "usuario": _usuario(),
        "equipo": _equipo(),
        "dwg": dwg_path if dwg_path else (_dwg_activo()[0] or ""),
        "dry_run": (not aplicado),
        "duracion_s": (round(float(duracion_s), 2)
                       if duracion_s is not None else None),
        "firma_config": _firma_config(cfg, fase),
        "auditoria_z": auditoria_z,
        "resultados": resultados,
    }
    fases_est = estado.setdefault("fases", {})
    reg = fases_est.setdefault(fase, {"nombre": FASES.get(fase, "?")})
    reg["nombre"] = FASES.get(fase, reg.get("nombre", "?"))
    reg["estado"] = nuevo_estado
    reg["ultima_ejecucion"] = entrada
    if nuevo_estado != "APROBADA":
        reg["aprobacion"] = None
    reg.pop("invalidada_por", None)

    C.append("fase {} -> {}".format(fase, nuevo_estado))
    C.append("firma config: " + entrada["firma_config"])
    C.append("auditoria Z: " + str(auditoria_z))

    # ---- invalidacion en cascada (solo si se aplico de verdad y fue OK) ---
    invalidadas = []
    if aplicado and ok:
        for d in _descendientes(fase):
            fd = fases_est.get(d)
            if not fd:
                continue
            if fd.get("estado") in ("EJECUTADA", "APLICADA", "APROBADA"):
                fd["estado"] = "DESACTUALIZADA"
                fd["invalidada_por"] = {"fase": fase, "timestamp": ts}
                invalidadas.append(d)
    if invalidadas:
        C.append("fases invalidadas (aguas abajo): " + ", ".join(invalidadas))
    elif aplicado and ok:
        C.append("fases invalidadas (aguas abajo): ninguna")

    hist = estado.setdefault("historial", [])
    hist.append({"fase": fase, "estado": nuevo_estado, "timestamp": ts,
                 "usuario": entrada["usuario"], "dry_run": entrada["dry_run"]})
    del hist[:-MAX_HISTORIAL]

    ok_w, aviso_w = _escribir_json_atomico(
        os.path.join(carpeta, NOMBRE_ESTADO), estado)
    C.append("estado_pipeline.json: " + aviso_w)
    if not ok_w:
        ok_cierre = False

    # ---- log a fichero ----------------------------------------------------
    try:
        dir_logs = os.path.join(carpeta, CARPETA_LOGS)
        if not os.path.isdir(dir_logs):
            os.makedirs(dir_logs)
        nombre_log = "F{}_{}_{}.log".format(
            fase, time.strftime("%Y%m%d_%H%M%S"), os.getpid())
        ruta_log = os.path.join(dir_logs, nombre_log)
        texto_total = (str(log_script or "") + "\n" + "\n".join(C)
                       + "\nVEREDICTO CIERRE: pendiente de escritura\n")
        for intento in range(REINTENTOS_IO):
            try:
                fl = open(ruta_log, "w", encoding="utf-8")
                try:
                    fl.write(texto_total)
                finally:
                    fl.close()
                C.append("log guardado: " + ruta_log)
                break
            except (PermissionError, OSError) as ex:
                if intento == REINTENTOS_IO - 1:
                    C.append("KO guardando log ({})".format(str(ex)[:80]))
                    ok_cierre = False
                else:
                    time.sleep(ESPERA_IO_S)
    except Exception as ex:
        C.append("KO preparando carpeta de logs: " + str(ex)[:120])
        ok_cierre = False

    C.append("{:<27}{:>7.2f} s".format("nodo_cierre",
                                       time.perf_counter() - t0))
    C.append("VEREDICTO CIERRE: {}".format("OK" if ok_cierre else "KO"))
    C.append(SEP)
    return [ok_cierre, str(log_script or "") + "\n" + "\n".join(C)]


# --------------------------------------------------------------------------- #
# Aprobacion manual 
# --------------------------------------------------------------------------- #

def aprobar_fase(fase, dwg_path=None, usuario=None):
    """Marca APROBADA una fase que este APLICADA. Devuelve [ok, mensaje]."""
    fase = str(fase)
    carpeta, lin = localizar_proyecto(dwg_path)
    if carpeta is None:
        return [False, "\n".join(lin)]
    cfg, aviso_cfg = leer_config(carpeta)
    if cfg is None:
        return [False, "KO config: " + aviso_cfg]
    estado, aviso_est = leer_estado(carpeta, cfg)
    reg = estado.get("fases", {}).get(fase)
    if not reg:
        return [False, "fase {} sin ejecuciones registradas".format(fase)]
    if reg.get("estado") != "APLICADA":
        return [False, "fase {} esta {} (solo se aprueba APLICADA)"
                .format(fase, reg.get("estado"))]
    reg["estado"] = "APROBADA"
    reg["aprobacion"] = {"usuario": usuario or _usuario(),
                         "timestamp": _ahora()}
    ok_w, aviso_w = _escribir_json_atomico(
        os.path.join(carpeta, NOMBRE_ESTADO), estado)
    if not ok_w:
        return [False, "KO escribiendo estado: " + aviso_w]
    return [True, "fase {} APROBADA por {} ({})".format(
        fase, reg["aprobacion"]["usuario"], reg["aprobacion"]["timestamp"])]


# --------------------------------------------------------------------------- #
# Plantilla de configuracion
# --------------------------------------------------------------------------- #

def crear_config_plantilla(carpeta, proyecto="MI_PROYECTO",
                           sobrescribir=False):
    """Genera config_proyecto.json de plantilla en 'carpeta'.
    Los valores {} son los de Estera donde se conocen; el resto queda
    marcado como <RELLENAR> y nodo_config lo detectara como KO hasta que
    se complete. Devuelve [ok, mensaje, ruta]."""
    ruta = os.path.join(carpeta, NOMBRE_CONFIG)
    if os.path.exists(ruta) and not sobrescribir:
        return [False, "ya existe (usa sobrescribir=True)", ruta]
    plantilla = {
        "version_esquema": VERSION_ESQUEMA,
        "proyecto": proyecto,
        "descripcion": "",
        "creado": _ahora(),
        "creado_por": _usuario(),
        "opciones": {
            "exigir_aprobacion": False,
            "exigir_prerrequisitos": False,
        },
        "parametros_comunes": {
            "scale_factor": 10000.0,
            "epsg": 25830,
            "cierre_virtual_max_m": 0.5,
        },
        "capas": {
            "contornos": MARCA_RELLENAR,
            "trackers": MARCA_RELLENAR,
            "ejes": "EJES",
        },
        "superficies": {
            "mdt": MARCA_RELLENAR,
            "mdt_recortado": MARCA_RELLENAR,
            "trackers": MARCA_RELLENAR,
        },
        "dwgs": {
            "mdt": MARCA_RELLENAR,
            "trackers": MARCA_RELLENAR,
            "volumenes": MARCA_RELLENAR,
            "analisis_ns": MARCA_RELLENAR,
            "analisis_eo": MARCA_RELLENAR,
            "analisis_trackers_ns": MARCA_RELLENAR,
            "analisis_trackers_eo": MARCA_RELLENAR,
        },
        "fases": {
            "0": {
                "dwg": "mdt",
                "superficie_mdt": MARCA_RELLENAR,
                "capa_contornos": "_contornos",
                "superficie_salida": MARCA_RELLENAR,
                "margen_extra_filtrado_m": 1.0,
                "anclar_contorno_original": "S",
                "paso_muestreo_borde_m": 1.0,
                "offset_borde_m": 1.0,
            },
            "1NS": {
                "dwg": "analisis_ns",
                "superficie_analisis": MARCA_RELLENAR,
                "capa_contorno": "_contornos offset",
                "capa_ejes": "_Lineas rotura",
                "tipo": "Trackers",
                "pendiente_max_pct": 4.0,
                "pendiente_aviso_pct": 3.0,
                "superficie_salida": "Slope_Analysis_MDT_NS",
                "opcion_puntos": 2,
                "pitch_min_m": 4.0,
                "pitch_max_m": 15.0,
                "iteraciones_subdivision": 2,
            },
            "1EO": {
                "dwg": "analisis_eo",
                "superficie_analisis": MARCA_RELLENAR,
                "capa_contorno": "_contornos offset",
                "capa_ejes": "_Lineas rotura",
                "tipo": "Trackers",
                "pendiente_max_pct": 4.0,
                "pendiente_aviso_pct": 3.0,
                "superficie_salida": "Slope_Analysis_MDT_EO",
                "opcion_puntos": 2,
                "pitch_min_m": 4.0,
                "pitch_max_m": 15.0,
                "iteraciones_subdivision": 2,
            },
            "2": {
                "dwg": "trackers",
                "capa_contornos": MARCA_RELLENAR,
                "capa_trackers": MARCA_RELLENAR,
                "capa_ejes": "EJES",
                "tol_agrupacion_m": 2.0,
                "extension_extremos_m": 1.0,
                "site": MARCA_RELLENAR,
                "estilo_alignment": "Standard",
                "label_set": "_No Labels",
                "add_curves": False,
                "superficie_mdt": MARCA_RELLENAR,
                "superficie_salida": MARCA_RELLENAR,
                "estilo_fl": "tracker alignment",
                "capa_perfiles": "0",
                "estilo_perfil_trackers": "LINEAS TRACKERS",
                "labelset_trackers":
                    "Inclinacion porcentaje Seguidor Modificado",
                "prefijo_trackers": "Trackers_Proyecto",
                "estilo_perfil_tn": "Perfil TN",
                "labelset_tn": "Inclinacion porcentaje TN",
                "prefijo_tn": "TN_",
                "origin_x": MARCA_RELLENAR,
                "origin_y": MARCA_RELLENAR,
                "col_spacing": 500.0,
                "row_spacing": 162.0,
                "pv_prefix": "PV",
                "bandset": "TRAKERS PROFILE LYNKA",
                "estilo_pv": "LYNKA PERFIL LONGITUDINAL",
                "patron_fl": "FL_T*",
                "tolerancia_proyeccion_m": 1.0,
                "estilo_proyeccion_fl": MARCA_RELLENAR,
                "suprimir_dialogos": True,
                "ruta_temp_lisp": "C:\\Temp\\proyeccion_fl.txt",
                "auto_ok_dialogos": True,
                "orientacion": MARCA_RELLENAR,
            },
            "3": {
                "dwg": "trackers",
                "modo": MARCA_RELLENAR,
                "patron_fl": "FL_T*",
                "superficie_mdt": MARCA_RELLENAR,
                "superficie_trackers": MARCA_RELLENAR,
                "pendiente_ns_pct": 1.5,
                "pendiente_eo_pct": 1.5,
                "pitch_m": 6.0,
                "margen_pitch_m": 2.0,
                "escalon_max_m": 0.15,
                "gap_contiguo_m": 5.0,
                "tol_extremos_m": 2.0,
                "tol_agrupacion_m": MARCA_RELLENAR,
                "etapa_correccion": MARCA_RELLENAR,
                "forzar": True,
                "max_pasadas_eo": 120,
                "solape_min_m": MARCA_RELLENAR,
                "ratio_dt_objetivo": MARCA_RELLENAR,
                "rugosidad_m": 0.05,
                "tol_rescate_m": 2.0,
                "tol_ratio": MARCA_RELLENAR,
                "pendiente_hincas_pct": 1.31,
                "deflexion_ala_pct": 13.96,
            },
            "1NST": {
                "dwg": "analisis_trackers_ns",
                "superficie_analisis": MARCA_RELLENAR,
                "capa_contorno": "_contornos offset",
                "capa_ejes": "_Lineas rotura",
                "tipo": "Trackers",
                "pendiente_max_pct": 4.0,
                "pendiente_aviso_pct": 3.0,
                "superficie_salida": "Slope_Analysis_Trackers_NS",
                "opcion_puntos": 2,
                "pitch_min_m": 4.0,
                "pitch_max_m": 15.0,
                "iteraciones_subdivision": 2,
            },
            "1EOT": {
                "dwg": "analisis_trackers_eo",
                "superficie_analisis": MARCA_RELLENAR,
                "capa_contorno": "_contornos offset",
                "capa_ejes": "_Lineas rotura",
                "tipo": "Trackers",
                "pendiente_max_pct": 4.0,
                "pendiente_aviso_pct": 3.0,
                "superficie_salida": "Slope_Analysis_Trackers_EO",
                "opcion_puntos": 2,
                "pitch_min_m": 4.0,
                "pitch_max_m": 15.0,
                "iteraciones_subdivision": 2,
            },
            "4": {
                "dwg": "volumenes",
                "superficie_trackers": MARCA_RELLENAR,
                "superficie_mdt": MARCA_RELLENAR,
                "rugosidad_mm": 100.0,
                "prefijo_volumen": "Volumen_MDT",
                "capa_contornos": "_contornos",
            },
            "5": {
                "dwg": "volumenes",
                "superficie_trackers": MARCA_RELLENAR,
                "superficie_mdt": MARCA_RELLENAR,
                "capa_contornos": "_contornos",
                "superficie_combinada": MARCA_RELLENAR,
                "offset_manchas_m": 0.10,
                "filtro_manchas_pct": 10,
                "pegar_mdt_base": "S",
                "intentos_offset": 3,
                "paso_offset_m": 0.05,
            },
            "6": {
                "dwg": "volumenes",
                "hojas_nombres": MARCA_RELLENAR,
                "filtro_dxf": "AECC_*TABLE*,ACAD_TABLE",
            },
        },
    }
    ok_w, aviso_w = _escribir_json_atomico(ruta, plantilla)
    if not ok_w:
        return [False, "KO escribiendo plantilla: " + aviso_w, ruta]
    return [True, "plantilla creada", ruta]


# --------------------------------------------------------------------------- #
# Config en Excel: la hoja es el editor humano, el JSON el contrato de
# maquina. leer_config() regenera el JSON solo cuando la hoja es mas
# reciente. El estado_pipeline.json sigue siendo SIEMPRE JSON.
# --------------------------------------------------------------------------- #

_CLAVES_MAQUINA = ("version_esquema", "creado", "creado_por",
                   "generado_desde_excel")


def _descripcion(ruta):
    if ruta in AYUDA:
        return AYUDA[ruta]
    ultimo = ruta.split(".")[-1]
    if ultimo in AYUDA:
        return AYUDA[ultimo]
    return ultimo.replace("_", " ")


def _fases_que_usan(clave):
    """Fases cuyo contrato (PARAMS_FASE) consume esta clave."""
    usos = []
    for f in FASES:
        if clave in PARAMS_FASE.get(f, []):
            usos.append(f)
    return usos


_TITULO_HOJA = {"mdt": "MDT", "trackers": "Trackers",
                "volumenes": "Volumenes",
                "analisis": "Analisis terreno",
                "analisis_ns": "Analisis terreno",
                "analisis_eo": "Analisis terreno",
                "analisis_trackers_ns": "Analisis trackers",
                "analisis_trackers_eo": "Analisis trackers"}


def _hojas_config(cfg):
    """Agrupa el contrato por hoja de destino (DWG donde se aplica).
    Devuelve lista ordenada de:
        (nombre_hoja, [(titulo_seccion, [(ruta, valor, fase_txt)])])
    Las fases sin 'dwg' declarado caen en la hoja 'Sin asignar'."""
    generales = []
    fila_gen = []
    for clave in ("proyecto", "descripcion"):
        if clave in cfg:
            fila_gen.append((clave, cfg.get(clave), "general"))
    for clave, valor in cfg.get("opciones", {}).items():
        fila_gen.append(("opciones." + clave, valor, "general"))
    generales.append(("Proyecto", fila_gen))
    mapa = (("parametros_comunes", "Parametros comunes"),
            ("capas", "Capas"),
            ("superficies", "Superficies"),
            ("dwgs", "DWGs de la cadena"))
    for raiz, titulo in mapa:
        filas = []
        for k, v in cfg.get(raiz, {}).items():
            if raiz == "dwgs":
                usos = [f for f, ps in cfg.get("fases", {}).items()
                        if isinstance(ps, dict) and ps.get("dwg") == k]
            else:
                usos = _fases_que_usan(k)
            filas.append((raiz + "." + k, v,
                          ", ".join(usos) if usos else "general"))
        if filas:
            generales.append((titulo, filas))

    hojas = [("Generales", generales)]
    indice = {"Generales": 0}
    for fase, params in cfg.get("fases", {}).items():
        dwg = (params or {}).get("dwg")
        nombre = _TITULO_HOJA.get(dwg, dwg) if dwg else "Sin asignar"
        if not nombre or nombre == MARCA_RELLENAR:
            nombre = "Sin asignar"
        if nombre not in indice:
            indice[nombre] = len(hojas)
            hojas.append((nombre, []))
        titulo = "Fase {} - {}".format(fase, FASES.get(fase, "?"))
        filas = [("fases." + fase + "." + k, v, fase)
                 for k, v in (params or {}).items()]
        hojas[indice[nombre]][1].append((titulo, filas))
    # 'Sin asignar' siempre al final (orden estable para el resto)
    hojas.sort(key=lambda h: 1 if h[0] == "Sin asignar" else 0)
    hojas = [(nh, s) for (nh, s) in hojas
             if any(filas for _t, filas in s)]
    return hojas


def crear_excel_plantilla(carpeta, proyecto="MI_PROYECTO",
                          sobrescribir=False):
    """Genera config_proyecto.xlsx (el editor comodo). Devuelve
    [ok, mensaje, ruta]."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.worksheet.datavalidation import DataValidation
    except Exception as ex:
        return [False, "openpyxl no disponible: " + str(ex)[:120], ""]
    ruta = os.path.join(carpeta, NOMBRE_CONFIG_XLSX)
    if os.path.exists(ruta) and not sobrescribir:
        return [False, "ya existe (usa sobrescribir=True)", ruta]

    import tempfile
    tmpd = tempfile.mkdtemp(prefix="plantilla_")
    try:
        crear_config_plantilla(tmpd, proyecto)
        cfg, _av = _leer_json(os.path.join(tmpd, NOMBRE_CONFIG))
    finally:
        try:
            shutil.rmtree(tmpd)
        except Exception as ex:
            pass_msg = "tmp sin borrar: " + str(ex)[:60]
    if cfg is None:
        return [False, "no pude construir la plantilla base", ruta]

    wb = Workbook()
    f_titulo = Font(name="Arial", size=14, bold=True, color="FFFFFF")
    f_leyenda = Font(name="Arial", size=9, italic=True, color="595959")
    f_cab = Font(name="Arial", size=10, bold=True)
    f_ruta = Font(name="Arial", size=8, color="808080")
    f_dato = Font(name="Arial", size=10)
    f_secc = Font(name="Arial", size=10, bold=True, color="1F4E5F")
    r_titulo = PatternFill("solid", fgColor="2F5B77")
    r_secc = PatternFill("solid", fgColor="E7EDF1")
    r_oblig = PatternFill("solid", fgColor="FFFF00")

    hojas = _hojas_config(cfg)
    coords = {}
    pendientes = []
    primera = True
    for nombre_hoja, secciones in hojas:
        if primera:
            ws = wb.active
            ws.title = nombre_hoja
            primera = False
        else:
            ws = wb.create_sheet(nombre_hoja)
        ws.merge_cells("A1:E1")
        ws["A1"] = ("Pipeline - Configuracion - hoja: "
                    + nombre_hoja)
        ws["A1"].font = f_titulo
        ws["A1"].fill = r_titulo
        ws.merge_cells("A2:E2")
        ws["A2"] = ("Edita SOLO la columna Valor. Amarillo = obligatorio. "
                    "Los valores escritos son ejemplos reales del formato. "
                    "Guarda y ejecuta: el JSON se regenera solo.")
        ws["A2"].font = f_leyenda
        cab = ("Ruta (no tocar)", "Fase", "Parametro", "Valor", "Notas")
        for i, texto in enumerate(cab):
            ws.cell(row=3, column=i + 1, value=texto).font = f_cab
        ws.freeze_panes = "A4"
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 8
        ws.column_dimensions["C"].width = 36
        ws.column_dimensions["D"].width = 26
        ws.column_dimensions["E"].width = 46

        validaciones = {}
        fila = 4
        for titulo, filas in secciones:
            c = ws.cell(row=fila, column=3, value="- " + titulo + " -")
            c.font = f_secc
            for col in range(1, 6):
                ws.cell(row=fila, column=col).fill = r_secc
            fila += 1
            for ruta_k, valor, fase_txt in filas:
                ws.cell(row=fila, column=1, value=ruta_k).font = f_ruta
                ws.cell(row=fila, column=2,
                        value=fase_txt).font = f_ruta
                ws.cell(row=fila, column=3,
                        value=_descripcion(ruta_k)).font = f_dato
                celda_v = ws.cell(row=fila, column=4)
                celda_v.font = f_dato
                coords[ruta_k] = (nombre_hoja, celda_v.coordinate)
                if ruta_k in ENLACES:
                    pendientes.append((celda_v, ws, fila, ruta_k))
                    fila += 1
                    continue
                marcador = None
                if ruta_k in NOTAS_FIJAS:
                    marcador = NOTAS_FIJAS[ruta_k]
                if valor == MARCA_RELLENAR:
                    if _es_opcional(ruta_k):
                        marcador = "opcional (vacio vale)"
                    elif ruta_k not in NOTAS_FIJAS:
                        celda_v.fill = r_oblig
                        marcador = "obligatorio"
                else:
                    celda_v.value = valor
                nota_txt = _nota(ruta_k, marcador)
                if nota_txt:
                    ws.cell(row=fila, column=5,
                            value=nota_txt).font = f_leyenda
                ultimo = ruta_k.split(".")[-1]
                if ultimo in DESPLEGABLES:
                    formula = DESPLEGABLES[ultimo]
                    if formula not in validaciones:
                        dv = DataValidation(type="list", formula1=formula,
                                            allow_blank=True)
                        ws.add_data_validation(dv)
                        validaciones[formula] = dv
                    validaciones[formula].add(celda_v)
                fila += 1
    ws_e = wb.create_sheet("Resumen")
    ws_e.merge_cells("B1:I1")
    ws_e["B1"] = "Pipeline - Resumen"
    ws_e["B1"].font = f_titulo
    ws_e["B1"].fill = r_titulo
    ws_e["B2"] = ("Solo lectura: parametros vigentes de cada script. "
                  "El conversor IGNORA esta hoja.")
    ws_e["B2"].font = f_leyenda
    GRID = (("0", "1NS", "1EO"), ("1NST", "1EOT", "2"),
            ("3", "4", "5"))
    COLS = ((2, 3), (5, 6), (8, 9))
    for c_i, columna in enumerate(GRID):
        col_n, col_v = COLS[c_i]
        fila = 4
        for f_id in columna:
            pref = "fases." + f_id + "."
            t = ws_e.cell(row=fila, column=col_n,
                          value="FASE " + f_id + " - "
                          + FASES.get(f_id, ""))
            t.font = f_secc
            for cc in (col_n, col_v):
                ws_e.cell(row=fila, column=cc).fill = r_secc
            fila += 1
            for rk in [k for k in coords if k.startswith(pref)]:
                hoja_o, cel_o = coords[rk]
                origen_c = wb[hoja_o][cel_o]
                cn = ws_e.cell(row=fila, column=col_n,
                               value=_descripcion(rk))
                cn.font = f_dato
                cv = ws_e.cell(row=fila, column=col_v,
                               value="='" + hoja_o + "'!" + cel_o)
                cv.font = f_dato
                cv.fill = _copiar(origen_c.fill)
                cv.number_format = origen_c.number_format
                fila += 1
            fila += 1
    for letra, ancho in (("B", 34), ("C", 20), ("E", 34), ("F", 20),
                         ("H", 34), ("I", 20), ("D", 2), ("G", 2)):
        ws_e.column_dimensions[letra].width = ancho
    ws_e.protection.sheet = True

    for celda_v, ws_p, fila_p, ruta_k in pendientes:
        origen = ENLACES[ruta_k]
        if origen in coords:
            hoja_o, cel_o = coords[origen]
            if hoja_o == ws_p.title:
                celda_v.value = "=" + cel_o
            else:
                celda_v.value = "='" + hoja_o + "'!" + cel_o
            ws_p.cell(row=fila_p, column=5,
                      value=_nota(ruta_k, "= enlazada a " + origen)
                      ).font = f_leyenda
        else:
            ws_p.cell(row=fila_p, column=5,
                      value="AVISO: origen " + origen
                      + " no encontrado").font = f_leyenda
    try:
        wb.save(ruta)
    except Exception as ex:
        return [False, "KO guardando xlsx: " + str(ex)[:120], ruta]
    return [True, "plantilla Excel creada", ruta]


def _valor_celda(v):
    if v is None:
        return MARCA_RELLENAR
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    if s == "":
        return MARCA_RELLENAR
    if s.upper() in ("TRUE", "VERDADERO"):
        return True
    if s.upper() in ("FALSE", "FALSO"):
        return False
    return s


def excel_a_config(carpeta):
    """Convierte config_proyecto.xlsx -> config_proyecto.json (escritura
    atomica). Devuelve [ok, aviso]."""
    try:
        from openpyxl import load_workbook
    except Exception as ex:
        return [False, "openpyxl no disponible: " + str(ex)[:120]]
    ruta_xlsx = os.path.join(carpeta, NOMBRE_CONFIG_XLSX)
    wb = None
    ultimo = ""
    for intento in range(3):
        try:
            wb = load_workbook(ruta_xlsx, data_only=True)
            break
        except Exception as ex:
            ultimo = str(ex)[:100]
            time.sleep(ESPERA_IO_S)
    if wb is None:
        return [False, "no pude abrir el xlsx: " + ultimo]
    cfg = {"version_esquema": VERSION_ESQUEMA}
    n_filas = 0
    for ws in wb.worksheets:
        if str(ws.title).strip().lower() in ("ejecutar", "resumen"):
            continue  # hoja de control/resumen: nunca contiene parametros
        idx_valor = 2  # compatibilidad con la hoja antigua de una pestana
        for fila in ws.iter_rows(values_only=True):
            if not fila or fila[0] is None:
                continue
            ruta_k = str(fila[0]).strip()
            if not ruta_k:
                continue
            if ruta_k == "Ruta (no tocar)":
                for i, celda in enumerate(fila):
                    if celda == "Valor":
                        idx_valor = i
                        break
                continue
            if " " in ruta_k:
                continue  # titulos/leyendas: las rutas no llevan espacios
            valor = _valor_celda(fila[idx_valor]
                                 if len(fila) > idx_valor else None)
            partes = ruta_k.split(".")
            nodo = cfg
            for p in partes[:-1]:
                nodo = nodo.setdefault(p, {})
                if not isinstance(nodo, dict):
                    return [False, "ruta invalida en la hoja: " + ruta_k]
            nodo[partes[-1]] = valor
            n_filas += 1
    cfg.setdefault("opciones", {})
    cfg.setdefault("fases", {})
    cfg["creado"] = _ahora()
    cfg["creado_por"] = _usuario()
    cfg["generado_desde_excel"] = _ahora()
    if n_filas == 0:
        return [False, "la hoja no tiene filas de parametros"]
    ok_w, aviso_w = _escribir_json_atomico(
        os.path.join(carpeta, NOMBRE_CONFIG), cfg)
    if not ok_w:
        return [False, "KO escribiendo JSON: " + aviso_w]
    return [True, "JSON regenerado ({} parametros)".format(n_filas)]


# --------------------------------------------------------------------------- #
# Autotest offline (sin AutoCAD): valida el contrato de punta a punta
# --------------------------------------------------------------------------- #

def autotest(verbose=True):
    """Suite offline. Devuelve (n_ok, n_ko, lineas)."""
    import tempfile
    L = []
    n_ok = [0]
    n_ko = [0]

    def check(nombre, cond, detalle=""):
        if cond:
            n_ok[0] += 1
            L.append("OK  " + nombre)
        else:
            n_ko[0] += 1
            L.append("KO  " + nombre + ("  -> " + detalle if detalle else ""))

    raiz = tempfile.mkdtemp(prefix="test_")
    sub = os.path.join(raiz, "02_DWG")
    os.makedirs(sub)
    dwg = os.path.join(sub, "TEST_Trackers.dwg")
    f = open(dwg, "w")
    f.write("dummy")
    f.close()

    # 1) sin config -> nodo_config KO con mensaje claro
    r = nodo_config("0", dwg_path=dwg)
    check("sin config -> KO", r[0] is False and "no se encontro" in r[1])

    # 2) plantilla + localizacion subiendo un nivel
    ok_p, msg_p, ruta_p = crear_config_plantilla(raiz, "TEST")
    check("crear plantilla", ok_p, msg_p)
    r = nodo_config("0", dwg_path=dwg)
    check("localiza config en nivel superior",
          (r[2] == raiz) and ("config encontrada" in r[1]))
    check("plantilla con <RELLENAR> -> KO parametros",
          r[0] is False and "faltan" in r[1])

    # 3) completar config y volver a validar
    cfg, _av = leer_config(raiz)
    cfg["fases"]["0"].update({
        "superficie_mdt": "MDT", "capa_contornos": "CONT",
        "superficie_salida": "MDT_REC"})
    cfg["fases"]["1NS"].update({"superficie_analisis": "MDT_REC"})
    cfg["fases"]["1EO"].update({"superficie_analisis": "MDT_REC"})
    cfg["fases"]["1NST"].update({"superficie_analisis": "SUP_TRK"})
    cfg["fases"]["1EOT"].update({"superficie_analisis": "SUP_TRK"})
    cfg["fases"]["2"].update({
        "orientacion": "NS",
        "origin_x": 295615.0, "origin_y": 4028361.0,
        "superficie_mdt": "MDT_REC", "capa_contornos": "CONT",
        "capa_trackers": "TRK", "superficie_salida": "SUP_TRK",
        "estilo_fl": "Basic", "col_tol_m": 2.0, "extension_ejes_m": 5.0})
    cfg["fases"]["4"].update({
        "superficie_trackers": "SUP_TRK", "superficie_mdt": "MDT_REC"})
    cfg["fases"]["5"].update({
        "superficie_trackers": "SUP_TRK", "superficie_mdt": "MDT_REC",
        "superficie_combinada": "MDT_MOD"})
    cfg["fases"]["3"].update({
        "modo": "EO", "superficie_mdt": "MDT_REC",
        "superficie_trackers": "SUP_TRK", "tol_agrupacion_m": 0.5,
        "etapa_correccion": "LONG+EO", "solape_min_m": 1.0,
        "ratio_dt_objetivo": 1.2, "tol_ratio": 0.1})
    okw, avw = _escribir_json_atomico(os.path.join(raiz, NOMBRE_CONFIG), cfg)
    check("escritura atomica config", okw, avw)
    check(".bak creado", os.path.exists(
        os.path.join(raiz, NOMBRE_CONFIG) + ".bak"))
    r0 = nodo_config("0", dwg_path=dwg)
    check("fase 0 config OK", r0[0] is True and len(r0) == 4 + 7)
    check("valores en orden", r0[4] == "MDT" and r0[7] == 1.0
          and r0[8] == "S")
    cfg, _av = leer_config(raiz)
    cfg["fases"]["0"]["dwg"] = "OTRO.dwg"
    _escribir_json_atomico(os.path.join(raiz, NOMBRE_CONFIG), cfg)
    r0b = nodo_config("0", dwg_path=dwg)
    check("guardarrail DWG: mismatch -> KO",
          r0b[0] is False and "corresponde al DWG" in r0b[1])
    cfg["dwgs"] = {"mdt": "TEST_Trackers.dwg",
                   "trackers": "TEST_Trackers.dwg",
                   "volumenes": "TEST_Trackers.dwg",
                   "analisis_ns": "TEST_Trackers.dwg",
                   "analisis_eo": "TEST_Trackers.dwg",
                   "analisis_trackers_ns": "TEST_Trackers.dwg",
                   "analisis_trackers_eo": "TEST_Trackers.dwg"}
    cfg["fases"]["0"]["dwg"] = "mdt"
    _escribir_json_atomico(os.path.join(raiz, NOMBRE_CONFIG), cfg)
    r0c = nodo_config("0", dwg_path=dwg)
    check("guardarrail DWG: coincide via clave dwgs",
          r0c[0] is True and "coincide" in r0c[1])
    cfg["dwgs"]["mdt"] = "TEST_Trackers"  # sin extension .dwg
    _escribir_json_atomico(os.path.join(raiz, NOMBRE_CONFIG), cfg)
    r0d = nodo_config("0", dwg_path=dwg)
    check("guardarrail DWG: tolerante a extension",
          r0d[0] is True and "coincide" in r0d[1])
    cfg["dwgs"]["mdt"] = "TEST_Trackers.dwg"
    _escribir_json_atomico(os.path.join(raiz, NOMBRE_CONFIG), cfg)

    # 4) cierre fase 0 aplicada
    rc = nodo_cierre("0", "log fase 0\n==== RESUMEN DE TIEMPOS ====",
                     resultados={"contornos": 4}, aplicado=True, ok=True,
                     auditoria_z="N/A", duracion_s=12.34, dwg_path=dwg)
    check("cierre fase 0", rc[0] is True and "APLICADA" in rc[1])
    est, _a = leer_estado(raiz)
    check("estado fase 0 = APLICADA",
          est["fases"]["0"]["estado"] == "APLICADA")
    check("log en Logs/", len(os.listdir(os.path.join(
        raiz, CARPETA_LOGS))) == 1)
    r1 = nodo_config("1NS", dwg_path=dwg)
    check("fase 1NS config OK", r1[0] is True and len(r1) == 4 + 11)
    check("fase 1NS valores en orden",
          r1[4] == "MDT_REC" and r1[7] == "Trackers" and r1[12] == 4.0)
    nodo_cierre("1NS", "log 1NS", aplicado=True, ok=True, dwg_path=dwg)
    nodo_cierre("1EO", "log 1EO", aplicado=True, ok=True, dwg_path=dwg)
    est1, _a1 = leer_estado(raiz)
    check("variantes NS y EO conviven en estado",
          est1["fases"].get("1NS", {}).get("estado") == "APLICADA"
          and est1["fases"].get("1EO", {}).get("estado") == "APLICADA")
    rx = nodo_config("1XX", dwg_path=dwg)
    check("fase desconocida -> KO",
          rx[0] is False and "desconocida" in rx[1])

    # 5) prerrequisitos: por defecto la puerta NO bloquea (v24)
    r3z = nodo_config("3", dwg_path=dwg)
    check("fase 3 sin fase 2, puerta off -> OK con AVISO",
          r3z[0] is True and "AVISO fase 2" in r3z[1])
    cfgp = leer_config(raiz)[0]
    cfgp.setdefault("opciones", {})["exigir_prerrequisitos"] = True
    _escribir_json_atomico(os.path.join(raiz, "config_proyecto.json"), cfgp)
    r3 = nodo_config("3", dwg_path=dwg)
    check("fase 3 sin fase 2, puerta on -> KO",
          r3[0] is False and "fase 2" in r3[1])
    r2 = nodo_config("2", dwg_path=dwg)
    check("fase 2 con fase 0 aplicada -> OK", r2[0] is True)
    rc2 = nodo_cierre("2", "log fase 2", resultados={"trackers": 1411},
                      aplicado=True, ok=True, auditoria_z="OK",
                      dwg_path=dwg)
    check("cierre fase 2", rc2[0] is True)
    r3b = nodo_config("3", dwg_path=dwg)
    check("fase 3 tras fase 2 -> OK",
          r3b[0] is True and r3b[4 + 13] is True)  # forzar en indice 17
    rc3 = nodo_cierre("3", "log fase 3", resultados={"kos": 0},
                      aplicado=True, ok=True, dwg_path=dwg)
    check("cierre fase 3", rc3[0] is True)
    nodo_cierre("4", "log fase 4", aplicado=True, ok=True, dwg_path=dwg)
    nodo_cierre("5", "log fase 5", aplicado=True, ok=True, dwg_path=dwg)
    r6 = nodo_config("6", dwg_path=dwg)
    check("fase 6 OK con opcional vacio",
          r6[0] is True and len(r6) == 4 + 2 and r6[4] == ""
          and "opcional" in r6[1])
    r1t = nodo_config("1NST", dwg_path=dwg)
    check("fase 1NST tras fase 3 -> OK",
          r1t[0] is True and len(r1t) == 4 + 11)
    nodo_cierre("1NST", "log 1NST", aplicado=True, ok=True, dwg_path=dwg)

    # 6) advertencia de firma: cambio config de fase 2 ya ejecutada
    cfg, _av = leer_config(raiz)
    cfg["fases"]["2"]["col_tol_m"] = 3.0
    _escribir_json_atomico(os.path.join(raiz, NOMBRE_CONFIG), cfg)
    r3c = nodo_config("3", dwg_path=dwg)
    check("advertencia por firma cambiada",
          "ADVERTENCIA" in r3c[1] and "fase 2" in r3c[1])

    # 7) invalidacion en cascada: re-aplicar fase 0 invalida 2 y 3
    rc0b = nodo_cierre("0", "re-ejecucion fase 0", aplicado=True, ok=True,
                       dwg_path=dwg)
    est, _a = leer_estado(raiz)
    check("cascada: fase 2 DESACTUALIZADA",
          est["fases"]["2"]["estado"] == "DESACTUALIZADA")
    check("cascada: fase 3 DESACTUALIZADA",
          est["fases"]["3"]["estado"] == "DESACTUALIZADA")
    check("cascada: fase 1NST DESACTUALIZADA",
          est["fases"]["1NST"]["estado"] == "DESACTUALIZADA")
    check("cascada listada en log", "invalidadas" in rc0b[1])
    r3d = nodo_config("3", dwg_path=dwg)
    check("fase 3 con fase 2 desactualizada -> KO",
          r3d[0] is False and "DESACTUALIZADA" in r3d[1])

    # 8) dry-run no invalida
    rc2b = nodo_cierre("2", "dry fase 2", aplicado=False, ok=True,
                       dwg_path=dwg)
    est, _a = leer_estado(raiz)
    check("dry-run -> EJECUTADA",
          est["fases"]["2"]["estado"] == "EJECUTADA")
    r3e = nodo_config("3", dwg_path=dwg)
    check("EJECUTADA (dry) no vale como prerrequisito", r3e[0] is False)
    cfgp = leer_config(raiz)[0]
    cfgp.setdefault("opciones", {})["exigir_prerrequisitos"] = False
    _escribir_json_atomico(os.path.join(raiz, "config_proyecto.json"), cfgp)
    r3e2 = nodo_config("3", dwg_path=dwg)
    check("EJECUTADA (dry) con puerta off -> OK con AVISO",
          r3e2[0] is True and "AVISO fase 2" in r3e2[1])
    cfgp["opciones"]["exigir_prerrequisitos"] = True
    _escribir_json_atomico(os.path.join(raiz, "config_proyecto.json"), cfgp)

    # 9) aprobar
    rc2c = nodo_cierre("2", "log fase 2 real", aplicado=True, ok=True,
                       dwg_path=dwg)
    ra = aprobar_fase("2", dwg_path=dwg)
    check("aprobar fase APLICADA", ra[0] is True and "APROBADA" in ra[1])
    ra2 = aprobar_fase("7", dwg_path=dwg)
    check("aprobar fase sin ejecutar -> KO", ra2[0] is False)

    # 10) exigir_aprobacion
    cfg, _av = leer_config(raiz)
    cfg["opciones"]["exigir_aprobacion"] = True
    _escribir_json_atomico(os.path.join(raiz, NOMBRE_CONFIG), cfg)
    r3f = nodo_config("3", dwg_path=dwg)
    check("con exigir_aprobacion, APROBADA vale", r3f[0] is True)

    # 11) rescate .bak con JSON corrupto
    ruta_e = os.path.join(raiz, NOMBRE_ESTADO)
    fe = open(ruta_e, "w", encoding="utf-8")
    fe.write("{corrupto")
    fe.close()
    est2, aviso2 = leer_estado(raiz)
    check("estado corrupto rescatado de .bak",
          "rescatado" in aviso2 and est2.get("fases", {}).get("2") is not None)

    # 12) historial acotado
    est3, _a = leer_estado(raiz)
    check("historial presente", len(est3.get("historial", [])) >= 5)

    # 13) Excel <-> JSON (si openpyxl esta disponible)
    try:
        import openpyxl  # noqa: F401
        hay_xlsx = True
    except Exception as ex:
        hay_xlsx = False
        L.append("AVISO: openpyxl no disponible, tests Excel omitidos ("
                 + str(ex)[:60] + ")")
    if hay_xlsx:
        raiz2 = tempfile.mkdtemp(prefix="pipeline_xlsx_")
        okx, msgx, rx = crear_excel_plantilla(raiz2, "TX")
        check("crear plantilla Excel", okx, msgx)
        res_conv = excel_a_config(raiz2)
        check("Excel -> JSON", res_conv[0], res_conv[1])
        cfx, avl = leer_config(raiz2)
        check("JSON generado legible y con datos",
              cfx is not None and cfx.get("proyecto") == "TX"
              and cfx["fases"]["3"]["pendiente_ns_pct"] == 1.5
              and cfx["fases"]["0"]["superficie_mdt"] == MARCA_RELLENAR
              and not any(" " in k for k in cfx))
        from openpyxl import load_workbook
        rxl = os.path.join(raiz2, NOMBRE_CONFIG_XLSX)
        wbx = load_workbook(rxl)
        nombres = wbx.sheetnames
        check("hojas por DWG + columna Fase",
              "MDT" in nombres and "Trackers" in nombres
              and "Volumenes" in nombres
              and "Analisis terreno" in nombres
              and "Analisis trackers" in nombres
              and "Sin asignar" not in nombres
              and any(c.value == "Fase" for c in wbx["Trackers"][3]))
        filas_at = [r[0] for r in wbx["Analisis trackers"].iter_rows(
            min_row=4, values_only=True) if r and r[0]]
        filas_te = [r[0] for r in wbx["Analisis terreno"].iter_rows(
            min_row=4, values_only=True) if r and r[0]]
        check("separacion terreno / trackers en pestanas",
              any(x.startswith("fases.1NST.") for x in filas_at)
              and any(x.startswith("fases.1NS.") for x in filas_te)
              and not any(x.startswith("fases.1NST.") for x in filas_te))

        # 14) arranque desde cero con SOLO la hoja Excel (bootstrap)
        raiz3 = tempfile.mkdtemp(prefix="pipeline_boot_")
        sub3 = os.path.join(raiz3, "02_DWG")
        os.makedirs(sub3)
        dwg3 = os.path.join(sub3, "BOOT.dwg")
        fb3 = open(dwg3, "w")
        fb3.write("dummy")
        fb3.close()
        crear_excel_plantilla(raiz3, "BOOT")
        rb = nodo_config("0", dwg_path=dwg3)
        check("bootstrap: proyecto localizado via Excel",
              rb[2] == raiz3 and "via Excel" in rb[1])
        check("bootstrap: JSON generado en la primera ejecucion",
              os.path.exists(os.path.join(raiz3, NOMBRE_CONFIG))
              and "regenerada desde Excel" in rb[1])
        fila_trk = None
        for rgen in wbx["Generales"].iter_rows(min_row=4,
                                               values_only=True):
            if rgen and rgen[0] == "dwgs.trackers":
                fila_trk = rgen
                break
        check("columna Fase en dwgs.*",
              fila_trk is not None and fila_trk[1] == "2, 3")
        f_sup = f_est = None
        for hx in wbx.worksheets:
            for filx in hx.iter_rows(min_row=4):
                if filx[0].value == "fases.3.superficie_mdt":
                    f_sup = str(filx[3].value or "")
                if filx[0].value == "fases.2.estilo_fl":
                    f_est = filx[3].value
        check("celdas enlazadas + estilo_fl fijo",
              f_sup.startswith("='Generales'!")
              and f_est == "tracker alignment")
        wse = wbx["Resumen"]
        wse["A20"] = "fases.0.superficie_mdt"
        wse["D20"] = "HACK"
        wbx.save(rxl)
        res_h = excel_a_config(raiz2)
        cfh, _avh = leer_config(raiz2)
        check("hoja Resumen presente e ignorada por el conversor",
              res_h[0] is True
              and cfh["fases"]["0"]["superficie_mdt"] != "HACK")
        tocado = False
        for hx in wbx.worksheets:
            for filx in hx.iter_rows(min_row=4):
                if filx[0].value == "fases.0.superficie_mdt":
                    filx[3].value = "MDTX"
                    tocado = True
                    break
            if tocado:
                break
        wbx.save(rxl)
        os.utime(rxl, (time.time() + 5, time.time() + 5))
        cfx2, avl2 = leer_config(raiz2)
        check("auto-regeneracion por mtime del Excel",
              tocado and "Excel" in avl2
              and cfx2["fases"]["0"]["superficie_mdt"] == "MDTX")

    L.append(SUB)
    L.append("RESULTADO AUTOTEST: {} OK / {} KO".format(n_ok[0], n_ko[0]))
    L.append("carpeta de pruebas: " + raiz)
    if verbose:
        print("\n".join(L))
    return n_ok[0], n_ko[0], L


if __name__ == "__main__":
    autotest(verbose=True)
