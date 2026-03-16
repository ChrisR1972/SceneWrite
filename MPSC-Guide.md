# Multi-Platform Setup Compiler (MPSC) - Agent Guide

Use this document when asking an AI agent to create a cross-platform installer for your application. Provide this along with your project details.

---

## What This Tool Does

MPSC is an Electron-based GUI application (located at `c:\Users\chris\Multi Platform Setup Compiler`) that compiles installer packages for **Windows (.exe)**, **macOS (.dmg)**, and **Linux (.deb/.rpm)** from a single project file.

- The packaged app is at: `c:\Users\chris\Multi Platform Setup Compiler\out\Multi-Platform Setup Compiler-win32-x64\Multi-Platform Setup Compiler.exe`
- You can also run it in dev mode: `npm start` from `c:\Users\chris\Multi Platform Setup Compiler`

---

## How To Use It

### 1. Create a `.mpsc` Project File

Create a JSON file with the `.mpsc` extension. This is the project definition that MPSC reads. Here is the full schema:

```json
{
  "appName": "Your Application Name",
  "appVersion": "1.0.0",
  "publisher": "Your Company or Name",
  "website": "https://yoursite.com",
  "description": "A short description of your application",
  "license": "./path/to/LICENSE.txt",
  "icon": "./path/to/icon.png",

  "files": [
    { "source": "./dist/**", "dest": "{app}" },
    { "source": "./README.md", "dest": "{app}" }
  ],

  "windows": {
    "installDir": "{pf}\\{appName}",
    "createDesktopShortcut": true,
    "createStartMenuEntry": true,
    "requireAdmin": true,
    "executable": "yourapp.exe"
  },

  "macos": {
    "bundleId": "com.yourcompany.yourapp",
    "category": "public.app-category.utilities",
    "executable": "yourapp",
    "minimumOS": "10.15",
    "signIdentity": ""
  },

  "linux": {
    "installDir": "/opt/{appName}",
    "categories": ["Utility"],
    "executable": "yourapp",
    "maintainer": "you@example.com",
    "dependencies": [],
    "section": "utils",
    "priority": "optional"
  },

  "installer": {
    "pages": ["welcome", "license", "directory", "install", "finish"],
    "allowCustomDir": true,
    "createUninstaller": true,
    "welcomeText": "Welcome to the setup wizard.",
    "finishText": "Installation complete.",
    "preInstallScript": "",
    "postInstallScript": ""
  }
}
```

### 2. Field Reference

#### Top-Level Fields

| Field | Required | Description |
|-------|----------|-------------|
| `appName` | Yes | Display name of your application |
| `appVersion` | Yes | Semantic version (e.g. `1.0.0`) |
| `publisher` | No | Company or author name |
| `website` | No | Project homepage URL |
| `description` | No | Short description shown in installers |
| `license` | No | Path to license text file (.txt, .rtf, .md) |
| `icon` | No | Path to app icon (.png, .ico, .icns) |
| `files` | Yes | Array of file entries to include (see below) |

#### File Entries

Each entry in the `files` array:

| Field | Description |
|-------|-------------|
| `source` | Path or glob pattern to source files. Use `/**` suffix for directories. |
| `dest` | Destination directory. Use `{app}` for the install root. |
| `exclude` | (Optional) Array of glob patterns to exclude. |

Examples:
```json
{ "source": "./build/**", "dest": "{app}" }
{ "source": "./assets/icon.png", "dest": "{app}" }
{ "source": "C:/MyProject/output/**", "dest": "{app}" }
```

#### Windows Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `installDir` | string | `{pf}\\{appName}` | Install location. `{pf}` = Program Files |
| `executable` | string | **required** | Main .exe filename |
| `createDesktopShortcut` | boolean | `true` | Create desktop shortcut |
| `createStartMenuEntry` | boolean | `true` | Add to Start Menu |
| `requireAdmin` | boolean | `true` | Request elevation |

#### macOS Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `bundleId` | string | **required** | Reverse-DNS identifier (e.g. `com.company.app`) |
| `category` | string | `utilities` | App Store category (see list below) |
| `executable` | string | **required** | Main binary filename |
| `minimumOS` | string | - | Minimum macOS version (e.g. `10.15`) |
| `signIdentity` | string | - | Code signing identity (leave empty for unsigned) |

macOS categories: `business`, `developer-tools`, `education`, `entertainment`, `finance`, `games`, `graphics-design`, `healthcare-fitness`, `lifestyle`, `music`, `productivity`, `utilities` (prefix each with `public.app-category.`)

#### Linux Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `installDir` | string | `/opt/{appName}` | Install location |
| `executable` | string | **required** | Main binary filename |
| `maintainer` | string | **required** | Email for .deb packages |
| `categories` | string[] | `["Utility"]` | Desktop categories |
| `dependencies` | string[] | `[]` | Package dependencies (e.g. `["libgtk-3-0"]`) |
| `section` | string | `utils` | Debian section |
| `priority` | string | `optional` | Package priority |

Linux categories: `AudioVideo`, `Audio`, `Video`, `Development`, `Education`, `Game`, `Graphics`, `Network`, `Office`, `Science`, `Settings`, `System`, `Utility`

#### Installer Pages

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `pages` | string[] | see below | Which wizard pages to show |
| `allowCustomDir` | boolean | `true` | Let user pick install directory |
| `createUninstaller` | boolean | `true` | Generate uninstaller |
| `welcomeText` | string | - | Custom welcome page text |
| `finishText` | string | - | Custom finish page text |
| `preInstallScript` | string | - | Script to run before install |
| `postInstallScript` | string | - | Script to run after install |

Available pages: `welcome`, `license`, `directory`, `components`, `install`, `finish`

### 3. Path Variables

Use these placeholders in paths -- they are resolved at build time:

| Variable | Meaning |
|----------|---------|
| `{appName}` | Application name |
| `{appVersion}` | Application version |
| `{publisher}` | Publisher name |
| `{pf}` | Program Files directory (Windows) |
| `{localappdata}` | Local AppData (Windows) |
| `{app}` | Application install directory |
| `{desktop}` | User desktop |
| `{startmenu}` | Start menu (Windows) |

---

## Prerequisites for Building

| Target | Tool Needed | Install Command |
|--------|-------------|-----------------|
| Windows .exe | NSIS (`makensis`) | Windows: https://nsis.sourceforge.io/Download -- macOS: `brew install nsis` -- Linux: `sudo apt install nsis` |
| macOS .dmg | `hdiutil` (macOS native) | Built-in on macOS. On other platforms, a `.tar.gz` of the `.app` bundle is created instead. |
| Linux .deb | None | Pure Node.js -- works on any OS. |
| Linux .rpm | `rpmbuild` (optional) | Linux: `sudo apt install rpm` -- macOS: `brew install rpm` -- Windows: skipped. |

---

## Example: Creating an Installer for Your Project

If you have a project at `C:\MyProject` with built output in `C:\MyProject\dist`, here is a complete `.mpsc` file:

```json
{
  "appName": "My Project",
  "appVersion": "1.0.0",
  "publisher": "Chris",
  "website": "https://example.com",
  "description": "My awesome cross-platform application",
  "license": "C:\\MyProject\\LICENSE.txt",
  "icon": "C:\\MyProject\\icon.png",
  "files": [
    { "source": "C:\\MyProject\\dist\\**", "dest": "{app}" }
  ],
  "windows": {
    "installDir": "{pf}\\My Project",
    "createDesktopShortcut": true,
    "createStartMenuEntry": true,
    "requireAdmin": true,
    "executable": "myproject.exe"
  },
  "macos": {
    "bundleId": "com.chris.myproject",
    "category": "public.app-category.utilities",
    "executable": "myproject"
  },
  "linux": {
    "installDir": "/opt/myproject",
    "categories": ["Utility"],
    "executable": "myproject",
    "maintainer": "chris@example.com"
  },
  "installer": {
    "pages": ["welcome", "license", "directory", "install", "finish"],
    "allowCustomDir": true,
    "createUninstaller": true
  }
}
```

Save this as `myproject.mpsc`, then open it in MPSC (via the GUI or by double-clicking), configure any settings, and hit **Build**.

---

## CLI Tool (Standalone -- runs on any OS)

There is a standalone CLI tool at `cli.mjs` that requires **only Node.js 18+** (no Electron, no npm install). Copy just this one file plus your `.mpsc` project file to any machine.

### Usage

```bash
node cli.mjs build <project.mpsc> [options]
```

### Options

| Flag | Description |
|------|-------------|
| `--platform <name>` | Target: `windows`, `macos`, or `linux`. Repeat for multiple. Default: all three. |
| `--output <dir>` | Output directory. Default: `./mpsc-output/<appName>` |

### Examples

```bash
# Build for all platforms
node cli.mjs build myapp.mpsc

# Build only macOS .dmg (must run on macOS for real .dmg)
node cli.mjs build myapp.mpsc --platform macos

# Build Windows + Linux, custom output folder
node cli.mjs build myapp.mpsc --platform windows --platform linux --output ./installers
```

### Running on macOS to create .dmg

To produce a real `.dmg` disk image (with drag-to-install Applications symlink), the CLI must run on macOS where `hdiutil` is available:

1. Copy `cli.mjs` and your `.mpsc` file to the Mac
2. Make sure the file paths in your `.mpsc` point to the right locations on the Mac
3. Run: `node cli.mjs build myapp.mpsc --platform macos`
4. Output: `./mpsc-output/<appName>/<name>-<version>-macos.dmg`

When run on Windows/Linux instead, the macOS target produces a `.tar.gz` containing the `.app` bundle as a fallback.

### Running on Windows to create .exe

Requires NSIS installed (https://nsis.sourceforge.io/Download). Then:

```bash
node cli.mjs build myapp.mpsc --platform windows
```

### Running anywhere to create .deb

The Linux `.deb` builder is pure Node.js with no external dependencies -- it works on any OS:

```bash
node cli.mjs build myapp.mpsc --platform linux
```

---

## For Agents: Step-by-Step

### GUI approach (Windows)

1. **Gather** the user's project details: app name, version, files to include, executables per platform.
2. **Create** a `.mpsc` file using the schema above with all required fields filled in.
3. **Save** it next to the user's project.
4. **Open** MPSC either via the packaged exe or `npm start` from `c:\Users\chris\Multi Platform Setup Compiler`.
5. **Load** the `.mpsc` file in the GUI (File > Open or the Open Project button on the start screen).
6. **Review** settings across tabs: General, Files, Windows, macOS, Linux, Installer Pages.
7. **Build** by clicking the Build button. Select target platforms (Windows/macOS/Linux). The build console shows real-time progress.
8. **Output** goes to `Documents\MPSC Output\{appName}\` by default.

### CLI approach (any OS)

1. **Create** a `.mpsc` file with all required fields.
2. **Run**: `node cli.mjs build project.mpsc --platform <target>`
3. **Output** appears in `./mpsc-output/<appName>/`

The GUI also supports creating projects from scratch using the template picker on the start screen (Desktop Application, CLI Tool, Background Service, or Blank).
