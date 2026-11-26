# 🎴 PokeBinder

Una aplicación de escritorio moderna y avanzada desarrollada con **PyQt6** y **Python** para gestionar tu colección de cartas Pokémon TCG, organizar álbumes (binders) interactivos de formato personalizable y explorar más de **95,000 cartas en 6 idiomas** con renderizado 3D físico interactivo.

---

## ✨ Características Principales

- **🌍 Catálogo Multilenguaje Completo (95,000+ Cartas)**:
  - Soporte integrado para cartas de **TCGDex** y **PokéAPI** en 6 idiomas: Español 🇪🇸, Inglés 🇬🇧, Japonés 🇯🇵, Francés 🇫🇷, Portugués 🇵🇹 y Chino 🇨🇳.
  - Filtros de búsqueda avanzada por nombre, rareza, tipo, edición, etapa e **idioma**.

- **🎴 Visor 3D Físico e Interactivo con Efectos Holográficos**:
  - Inclinación 3D realista por física de inercia y ratón sin recortes de bordes.
  - Reversa personalizada (`assets/icons/carta.jpg`).
  - Carga y renderizado dinámico en **Alta Definición (Full HD)** con indicador visual en tiempo real.

- **📖 Binders (Álbumes) Interactivos y Personalizables**:
  - Modalidades de página personalizables: **2x2, 3x3, 3x4 y 4x4**.
  - **Drag & Drop**: Arrastra y suelta cartas fácilmente desde tu colección hacia cualquier posición del Binder.
  - **Selección Múltiple y Botón "Quitar"**: Selecciona una o varias cartas en el Binder y quítalas de la carpeta sin borrarlas de tu colección personal.
  - Insignia de idioma (`ES 🇪🇸`, `JA 🇯🇵`, etc.) al lado de cada carta en la barra lateral.

- **⚡ Motor de Imágenes `.webp` de Alto Rendimiento**:
  - Conversión e integración nativa con `Pillow` (calidad 85-90%).
  - Ahorro de espacio en disco del 85-90% por imagen (imágenes livianas de ~50-70 KB).

---

## 🛠️ Requisitos del Sistema

- **Sistema Operativo**: Windows 10 / 11 (64-bit).
- **Python**: v3.10 o superior.

---

## 🚀 Instalación y Uso Local

1. **Clonar el repositorio**:
   ```bash
   git clone https://github.com/Media-Hub-Site/PokeBinderInventory.git
   cd PokeBinder
   ```

2. **Crear y activar el entorno virtual**:
   ```bash
   python -m venv venv
   # En Windows:
   venv\Scripts\activate
   ```

3. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Ejecutar la aplicación**:
   ```bash
   python main.py
   ```

---

## 📦 Compilación a Ejecutable (PyInstaller)

Para generar la versión ejecutable independiente lista para ser distribuida o integrada con **Inno Setup**:

```bash
pyinstaller --noconfirm --onedir --windowed ^
  --name "PokeBinder" ^
  --icon "assets/icons/TCG_Logo.ico" ^
  --add-data "assets;assets" ^
  --add-data "PokeDatabase.db;." ^
  main.py
```

La carpeta compilada se generará en `dist/PokeBinder/`.

---

## 🛠️ Empaquetado con Inno Setup

Para convertir la carpeta `dist/PokeBinder/` en un instalador ejecutable `.exe` para Windows:

1. Instala **Inno Setup 6**.
2. Abre `installer.iss`.
3. Compila el script de Inno Setup para generar el instalador ejecutable final `Output/PokeBinder-Setup.exe`.

---

## 📝 Licencia

Este proyecto se distribuye bajo la licencia MIT.
