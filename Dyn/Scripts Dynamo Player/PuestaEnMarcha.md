# Pipeline — Puesta en marcha y ejecución

Manual operativo. 

## Puesta en marcha (una vez)

Hay tres piezas y solo dos las tocas tú:

| Pieza | Cuántas | Dónde vive | Quién la mantiene |
|---|---|---|---|
| `pipeline.py` (módulo) | **una para todos los proyectos** | Python interno de Dynamo (lo pone `instalar.bat`) | Se instala una vez por usuario y máquina |
| `config_proyecto.xlsx` | **una por proyecto** | Carpeta raíz del proyecto | La rellenas tú por proyecto |
| Los `.dyn` | Donde quieras (la carpeta que apuntas en el Player) | Se actualizan cuando llega una versión nueva |

El módulo no sabe nada de los proyectos, y los proyectos no saben nada del módulo: al ejecutar, los nodos CONFIG y CIERRE de cada `.dyn` 
importan `pipeline.py` de donde esté instalado y localizan el proyecto subiendo desde el DWG activo.

### 1. Instalar el módulo `pipeline.py` (una vez por usuario y máquina)

**Qué hace `instalar.bat`.** Copia `pipeline.py` a `%APPDATA%\Python\Python39\site-packages` — la carpeta que el Python interno de Dynamo (CPython 3.9)
**Pasos.**

1. Deja `pipeline.py` e `instalar.bat` **juntos** en cualquier carpeta
   (recomendado: la carpeta compartida donde están los `.dyn`)
2. Cierra Civil 3D si lo tienes abierto (Dynamo carga el módulo al
   arrancar; si estaba abierto, seguirá usando la copia vieja hasta que
   lo reinicies).
3. Doble clic en `instalar.bat`. Se abre una ventana negra que muestra
   origen y destino y termina en `[OK] Instalado`. Pulsa una tecla para
   cerrarla.
4. Abre Civil 3D y ejecuta cualquier fase desde el Player. La primera
   línea del log del nodo CONFIG debe decir
   `pipeline.py: importado desde C:\Users\<tu usuario>\AppData\Roaming\Python\Python39\site-packages\pipeline.py`.
  

**Comprobación manual (opcional).** 
En un cmd: `dir "%APPDATA%\Python\Python39\site-packages\pipeline.py"` debe listar el fichero.

**Si el instalador dice `[KO] No encuentro pipeline.py junto a este .bat`:** los dos ficheros no están en la misma carpeta; júntalos y repite.
**Si dice `[KO] La copia ha fallado`:** permisos sobre la carpeta destino; ciérralo todo y repite, o crea la carpeta a mano
(`%APPDATA%\Python\Python39\site-packages`) y vuelve a lanzar.

**Cuándo hay que repetirlo.**

- Cuando recibas una versión nueva de `pipeline.py`: sustituye el
  fichero junto al `.bat` y doble clic otra vez. Cada usuario, en su
  máquina.

**Lo que NO tienes que hacer.** No hay que copiar el módulo a las carpetas de los proyectos. Si alguna vez ves un `pipeline.py` suelto dentro de una carpeta de proyecto puedes borrarlo.

**Ficheros que llegan con cada entrega del módulo:** `pipeline.py`,
`instalar.bat`, `cabecera_nodos_dynamo.py` (solo referencia: es el
código que ya llevan dentro los nodos CONFIG y CIERRE de los `.dyn`;
no hay que pegarlo en ningún sitio salvo que se cree un script nuevo)
y este README.

### 2. La configuración del proyecto (una vez por proyecto)

**Copia la plantilla.** Copia `config_proyecto.plantilla.xlsx` a la carpeta raíz del proyecto (junto a los DWG o hasta 2 niveles por encima) con el nombre exacto `config_proyecto.xlsx`. 
Ábrela y rellena por pestañas: los amarillos son obligatorios, los desplegables te guían, y en Generales pon los nombres de fichero de los DWG de la cadena. Guarda. 
(El `config_proyecto.json` se genera y actualiza solo; no lo edites a mano.)


**Qué se crea y cuándo.** `config_proyecto.json` lo genera el nodo
CONFIG en la primera ejecución a partir de tu
`config_proyecto.xlsx`, y lo regenera cada vez que guardas la hoja.
`estado_pipeline.json` y la carpeta `Logs\` los escribe el nodo
CIERRE al final de cada ejecución. 

## Ejecución del proceso

Orden del pipeline y DWG de cada fase:

| Fase | Qué hace | DWG (clave en config) | Script |
|---|---|---|---|
| 0 | Recorte MDT | `mdt` | 0_DP_RecorteMDT_v01 |
| 1NS / 1EO | Análisis vs terreno | `analisis_ns` / `analisis_eo` | 1_DP_Slope_Analysis_Unificado |
| 2 | Superficie de trackers | `trackers` | 2_DP_TrackersSuperficie... |
| 3 | Corrección de pendientes | `trackers` | 3_DP_CorreccionPendientes |
| 1NST / 1EOT | Análisis vs trackers | `analisis_trackers_ns` / `_eo` | mismo script 1 *(selector pendiente)* |
| 4 / 5 / 6 | Volúmenes / Zonas / Tablas | `volumenes` | 4_..._v03 / 5_..._v03 / 6_DP_TablasExcel |



El ciclo de cada fase es siempre el mismo:

1. **Activa el DWG que toca** (pestaña de Civil 3D). El Player ejecuta
   cada ▶ sobre el documento activo; si te equivocas de DWG, el nodo de
   config lo canta con un KO que nombra el esperado y el activo.
2. **Ejecuta** el script (Player o Dynamo, como siempre). 
3. **Lee los dos logs  — ahora en el propio panel del Player al
   terminar 
4. **En los análisis**, cambia el input de orientación NS→EO y repite:
   quedan dos registros separados. 

**Cambiar parámetros a mitad de proyecto:** edita la hoja Excel,
**guarda**, y ejecuta — el JSON se regenera solo 

**Aviso conocido (inofensivo):** al usar el Player puede aparecer un
diálogo de AutoCAD "El subproceso de llamada debe ser STA": el backup automático de Dynamo (su temporizador interno de copias de seguridad).
No afecta al resultado de las ejecuciones pero es peligroso: cerrarlo con la X termina AutoCAD puede acabar cerrándolo — con el DWG sin guardar. 
La única vía fiable es eliminarlo de raíz desactivando el backup:Desde Dynamo: ajustes → Preferences → General → grupo Backup, intervalo al máximo o copias a 0 . 

**Cuando algo falla:** el veredicto KO del Watch de config dice qué es (parámetro sin rellenar, prerrequisito sin cumplir, DWG equivocado,
módulo no encontrado con las rutas probadas). El histórico completo de ejecuciones está en la carpeta `Logs\` del proyecto.
