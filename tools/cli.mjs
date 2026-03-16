#!/usr/bin/env node
/**
 * MPSC CLI - Multi-Platform Setup Compiler (standalone)
 *
 * Usage:
 *   node cli.mjs build <project.mpsc> [--platform windows|macos|linux] [--output <dir>]
 *
 * Runs on any OS with Node.js 18+. No Electron required.
 * On macOS, produces real .dmg files via hdiutil.
 */

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import zlib from 'node:zlib';
import { execFile, execFileSync } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

const execFileAsync = promisify(execFile);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ─── Utilities ──────────────────────────────────────────────────────────────

function log(level, msg, platform) {
  const tag = platform ? `[${platform}] ` : '';
  const prefix = { info: '  ', warn: '⚠ ', error: '✗ ', success: '✓ ' }[level] || '  ';
  console.log(`${prefix}${tag}${msg}`);
}

function sanitizeFilename(name) {
  return name.replace(/[^a-zA-Z0-9._-]/g, '_').toLowerCase();
}

function resolveVariables(template, project) {
  const vars = {
    '{appName}': project.appName,
    '{appVersion}': project.appVersion,
    '{publisher}': project.publisher || '',
    '{website}': project.website || '',
    '{description}': project.description || '',
  };
  let result = template;
  for (const [key, value] of Object.entries(vars)) {
    result = result.split(key).join(value);
  }
  return result;
}

function escapeNsis(str) {
  return str
    .replace(/\$/g, '$$$$')
    .replace(/"/g, '$\\"')
    .replace(/\r\n/g, '$\\r$\\n')
    .replace(/\n/g, '$\\n')
    .replace(/\r/g, '$\\r')
    .replace(/\t/g, '$\\t');
}

function escapeXml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

// ─── File operations ────────────────────────────────────────────────────────

function copyDirRecursive(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    const lstat = fs.lstatSync(srcPath);
    if (lstat.isSymbolicLink()) {
      const target = fs.readlinkSync(srcPath);
      try { fs.symlinkSync(target, destPath); } catch { /* skip if symlink fails */ }
    } else if (lstat.isDirectory()) {
      copyDirRecursive(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

function copyFiles(sourcePatterns, stagingDir) {
  for (const entry of sourcePatterns) {
    const sourcePath = entry.source.replace(/\/\*\*$/, '');
    const destDir = path.join(stagingDir, entry.dest.replace(/\{app\}/g, ''));
    fs.mkdirSync(destDir, { recursive: true });
    if (fs.existsSync(sourcePath)) {
      const stat = fs.statSync(sourcePath);
      if (stat.isDirectory()) copyDirRecursive(sourcePath, destDir);
      else fs.copyFileSync(sourcePath, path.join(destDir, path.basename(sourcePath)));
    }
  }
}

// ─── Tar/Gz/Ar archives (pure Node.js) ─────────────────────────────────────

function writeString(buf, offset, str, len) {
  buf.write(str.slice(0, len - 1), offset, len, 'utf-8');
}

function writeOctal(buf, offset, value, len) {
  buf.write(value.toString(8).padStart(len - 1, '0'), offset, len - 1, 'ascii');
  buf[offset + len - 1] = 0;
}

function createTarBuffer(baseDir) {
  const buffers = [];
  function addEntry(filePath, stat) {
    const rel = path.relative(baseDir, filePath).replace(/\\/g, '/');
    const header = Buffer.alloc(512, 0);
    writeString(header, 0, rel, 100);
    writeOctal(header, 100, stat.isDirectory() ? 0o755 : 0o644, 8);
    writeOctal(header, 108, 0, 8);
    writeOctal(header, 116, 0, 8);
    writeOctal(header, 124, stat.isDirectory() ? 0 : stat.size, 12);
    writeOctal(header, 136, Math.floor(stat.mtimeMs / 1000), 12);
    header[156] = stat.isDirectory() ? 53 : 48;
    header.write('ustar', 257, 5, 'ascii');
    header[262] = 0x20;
    header[263] = 0x20;
    header.fill(0x20, 148, 156);
    let cksum = 0;
    for (let i = 0; i < 512; i++) cksum += header[i];
    writeOctal(header, 148, cksum, 7);
    header[155] = 0x20;
    buffers.push(header);
    if (!stat.isDirectory()) {
      const content = fs.readFileSync(filePath);
      buffers.push(content);
      const pad = 512 - (content.length % 512);
      if (pad < 512) buffers.push(Buffer.alloc(pad, 0));
    }
  }
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      addEntry(full, fs.statSync(full));
      if (entry.isDirectory()) walk(full);
    }
  }
  walk(baseDir);
  buffers.push(Buffer.alloc(1024, 0));
  return Buffer.concat(buffers);
}

function createTarGz(sourceDir, outputFile) {
  fs.writeFileSync(outputFile, zlib.gzipSync(createTarBuffer(sourceDir)));
}

function createArArchive(files) {
  const buffers = [Buffer.from('!<arch>\n')];
  for (const file of files) {
    const header = Buffer.alloc(60);
    header.write(file.name.padEnd(16, ' '), 0, 16, 'ascii');
    header.write(Math.floor(Date.now() / 1000).toString().padEnd(12, ' '), 16, 12, 'ascii');
    header.write('0'.padEnd(6, ' '), 28, 6, 'ascii');
    header.write('0'.padEnd(6, ' '), 34, 6, 'ascii');
    header.write('100644'.padEnd(8, ' '), 40, 8, 'ascii');
    header.write(file.data.length.toString().padEnd(10, ' '), 48, 10, 'ascii');
    header.write('`\n', 58, 2, 'ascii');
    buffers.push(header, file.data);
    if (file.data.length % 2 !== 0) buffers.push(Buffer.from('\n'));
  }
  return Buffer.concat(buffers);
}

// ─── Validation ─────────────────────────────────────────────────────────────

function validateProject(project, platforms) {
  const errors = [];
  if (!project.appName?.trim()) errors.push({ message: 'appName is required' });
  if (!project.appVersion?.trim()) errors.push({ message: 'appVersion is required' });
  if (!project.files?.length) errors.push({ message: 'At least one file entry is required' });
  if (platforms.includes('windows') && !project.windows?.executable?.trim())
    errors.push({ message: 'windows.executable is required', platform: 'windows' });
  if (platforms.includes('macos')) {
    if (!project.macos?.bundleId?.trim()) errors.push({ message: 'macos.bundleId is required', platform: 'macos' });
    if (!project.macos?.executable?.trim()) errors.push({ message: 'macos.executable is required', platform: 'macos' });
  }
  if (platforms.includes('linux')) {
    if (!project.linux?.executable?.trim()) errors.push({ message: 'linux.executable is required', platform: 'linux' });
    if (!project.linux?.maintainer?.trim()) errors.push({ message: 'linux.maintainer is required', platform: 'linux' });
  }
  return errors;
}

// ─── Windows Builder (NSIS) ─────────────────────────────────────────────────

function findMakensis() {
  const paths = {
    win32: ['makensis', 'C:\\Program Files (x86)\\NSIS\\makensis.exe', 'C:\\Program Files\\NSIS\\makensis.exe'],
    darwin: ['makensis', '/usr/local/bin/makensis', '/opt/homebrew/bin/makensis'],
    linux: ['makensis', '/usr/bin/makensis', '/usr/local/bin/makensis'],
  };
  for (const candidate of (paths[process.platform] || paths.linux)) {
    try {
      if (candidate === 'makensis') { execFileSync('makensis', ['-VERSION'], { stdio: 'pipe' }); return candidate; }
      if (fs.existsSync(candidate)) return candidate;
    } catch { /* continue */ }
  }
  throw new Error('NSIS (makensis) not found. Install from https://nsis.sourceforge.io/Download');
}

function nsisString(value) { return `"${escapeNsis(value)}"`; }

async function buildWindows(project, stagingDir, outputDir, logFn) {
  logFn('Copying files...');
  copyFiles(project.files, stagingDir);

  let licenseFile = null;
  if (project.license && fs.existsSync(project.license)) {
    licenseFile = path.join(stagingDir, path.basename(project.license));
    fs.copyFileSync(project.license, licenseFile);
  }
  let iconFile = null;
  if (project.icon && fs.existsSync(project.icon)) {
    iconFile = path.join(stagingDir, path.basename(project.icon));
    fs.copyFileSync(project.icon, iconFile);
  }

  const appName = project.appName;
  const appVersion = project.appVersion;
  const executable = project.windows.executable;
  let installDir = project.windows.installDir || '{pf}\\{appName}';
  installDir = installDir.replace(/\{pf\}/gi, '$PROGRAMFILES64').replace(/\{appName\}/g, appName).replace(/\\\\/g, '\\');
  const outFileName = `${sanitizeFilename(appName)}-${sanitizeFilename(appVersion)}-setup.exe`;
  const pages = project.installer?.pages || ['welcome', 'license', 'directory', 'install', 'finish'];
  const hasLicense = pages.includes('license') && !!licenseFile;
  const hasDir = pages.includes('directory') && project.installer?.allowCustomDir !== false;

  const welcomeText = project.installer?.welcomeText || '';
  const finishText = project.installer?.finishText || '';

  const L = [];
  L.push(
    '!include "MUI2.nsh"', '',
    'ManifestDPIAware true', '',
    `!define PRODUCT_NAME ${nsisString(appName)}`,
    `!define PRODUCT_VERSION ${nsisString(appVersion)}`,
    `!define PRODUCT_PUBLISHER ${nsisString(project.publisher || '')}`,
    `!define PRODUCT_WEB_SITE ${nsisString(project.website || '')}`,
    '', 'Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"',
    `OutFile ${nsisString(outFileName)}`,
    `InstallDir "${installDir}"`, '',
    project.windows.requireAdmin ? 'RequestExecutionLevel admin' : 'RequestExecutionLevel user', '',
  );
  if (iconFile) L.push(`!define MUI_ICON ${nsisString(path.basename(iconFile))}`, `!define MUI_UNICON ${nsisString(path.basename(iconFile))}`, '');
  if (hasLicense) L.push(`LicenseData ${nsisString(path.basename(licenseFile))}`, '');

  L.push('!define MUI_ABORTWARNING', '');

  for (const page of pages) {
    if (page === 'welcome') {
      L.push('!define MUI_WELCOMEPAGE_TITLE "Welcome to ${PRODUCT_NAME} Setup"');
      if (welcomeText) L.push(`!define MUI_WELCOMEPAGE_TEXT ${nsisString(welcomeText)}`);
      L.push('!insertmacro MUI_PAGE_WELCOME', '');
    }
    else if (page === 'license' && hasLicense) { L.push(`!insertmacro MUI_PAGE_LICENSE "${path.basename(licenseFile)}"`, ''); }
    else if (page === 'directory' && hasDir) { L.push('!insertmacro MUI_PAGE_DIRECTORY', ''); }
    else if (page === 'components') { L.push('!insertmacro MUI_PAGE_COMPONENTS', ''); }
    else if (page === 'install') { L.push('!insertmacro MUI_PAGE_INSTFILES', ''); }
    else if (page === 'finish') {
      L.push('!define MUI_FINISHPAGE_TITLE "Completing ${PRODUCT_NAME} Setup"');
      if (finishText) L.push(`!define MUI_FINISHPAGE_TEXT ${nsisString(finishText)}`);
      L.push('!insertmacro MUI_PAGE_FINISH', '');
    }
  }
  if (project.installer?.createUninstaller) L.push('!insertmacro MUI_UNPAGE_CONFIRM', '!insertmacro MUI_UNPAGE_INSTFILES', '');

  L.push('!insertmacro MUI_LANGUAGE "English"', '');
  if (project.windows.requireAdmin) L.push('Function .onInit', '  SetShellVarContext all', 'FunctionEnd', '');

  L.push('Section "Install"', '  SetOutPath "$INSTDIR"', '  File /r /x "*.nsi" "*.*"', '');
  if (project.installer?.createUninstaller) L.push('  WriteUninstaller "$INSTDIR\\Uninstall.exe"', '');
  if (project.windows.createDesktopShortcut && executable) L.push(`  CreateShortCut "$DESKTOP\\${escapeNsis(appName)}.lnk" "$INSTDIR\\${escapeNsis(executable)}"`, '');
  if (project.windows.createStartMenuEntry && executable) L.push(`  CreateDirectory "$SMPROGRAMS\\${escapeNsis(appName)}"`, `  CreateShortCut "$SMPROGRAMS\\${escapeNsis(appName)}\\${escapeNsis(appName)}.lnk" "$INSTDIR\\${escapeNsis(executable)}"`, '');
  if (project.installer?.createUninstaller) {
    const rk = project.windows.requireAdmin ? 'HKLM' : 'HKCU';
    const rp = `Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${escapeNsis(appName)}`;
    L.push(
      `  WriteRegStr ${rk} "${rp}" "DisplayName" "${escapeNsis(appName)}"`,
      `  WriteRegStr ${rk} "${rp}" "UninstallString" "$\\"$INSTDIR\\Uninstall.exe$\\""`,
      `  WriteRegStr ${rk} "${rp}" "DisplayVersion" "${escapeNsis(appVersion)}"`,
      `  WriteRegStr ${rk} "${rp}" "Publisher" "${escapeNsis(project.publisher || '')}"`,
      `  WriteRegDWORD ${rk} "${rp}" "NoModify" 1`, `  WriteRegDWORD ${rk} "${rp}" "NoRepair" 1`, '',
    );
  }
  L.push('SectionEnd', '');
  if (project.installer?.createUninstaller) {
    const rk = project.windows.requireAdmin ? 'HKLM' : 'HKCU';
    const rp = `Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${escapeNsis(appName)}`;
    L.push('Section "Uninstall"', '');
    if (project.windows.requireAdmin) L.push('  SetShellVarContext all', '');
    if (project.windows.createDesktopShortcut) L.push(`  Delete "$DESKTOP\\${escapeNsis(appName)}.lnk"`, '');
    if (project.windows.createStartMenuEntry) L.push(`  Delete "$SMPROGRAMS\\${escapeNsis(appName)}\\${escapeNsis(appName)}.lnk"`, `  RMDir "$SMPROGRAMS\\${escapeNsis(appName)}"`, '');
    L.push('  RMDir /r "$INSTDIR"', `  DeleteRegKey ${rk} "${rp}"`, '', 'SectionEnd');
  }

  const nsiPath = path.join(stagingDir, 'installer.nsi');
  fs.writeFileSync(nsiPath, L.join('\r\n'), 'utf-8');
  logFn('Generated NSIS script');

  const makensis = findMakensis();
  logFn(`Running ${makensis}...`);
  await execFileAsync(makensis, ['/V2', nsiPath], { cwd: stagingDir });

  const finalPath = path.join(outputDir, outFileName);
  const stagingExe = path.join(stagingDir, outFileName);
  if (fs.existsSync(stagingExe)) fs.copyFileSync(stagingExe, finalPath);
  logFn(`Created: ${finalPath}`);
  return finalPath;
}

// ─── macOS Builder (.app + .dmg) ────────────────────────────────────────────

function generateInfoPlist(project) {
  const { appName, appVersion, description, publisher } = project;
  const { bundleId, category, executable, minimumOS } = project.macos;
  let plist = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>CFBundleName</key>
\t<string>${escapeXml(appName)}</string>
\t<key>CFBundleDisplayName</key>
\t<string>${escapeXml(appName)}</string>
\t<key>CFBundleIdentifier</key>
\t<string>${escapeXml(bundleId)}</string>
\t<key>CFBundleVersion</key>
\t<string>${escapeXml(appVersion)}</string>
\t<key>CFBundleShortVersionString</key>
\t<string>${escapeXml(appVersion)}</string>
\t<key>CFBundleExecutable</key>
\t<string>${escapeXml(executable)}</string>
\t<key>CFBundlePackageType</key>
\t<string>APPL</string>
\t<key>LSApplicationCategoryType</key>
\t<string>${escapeXml(category)}</string>
\t<key>NSHumanReadableCopyright</key>
\t<string>${escapeXml(publisher || '')}</string>`;
  if (minimumOS) plist += `\n\t<key>LSMinimumSystemVersion</key>\n\t<string>${escapeXml(minimumOS)}</string>`;
  if (project.icon) plist += `\n\t<key>CFBundleIconFile</key>\n\t<string>${escapeXml(path.basename(project.icon))}</string>`;
  plist += '\n</dict>\n</plist>\n';
  return plist;
}

async function buildMacOS(project, stagingDir, outputDir, logFn) {
  const appName = project.appName;
  const bundleName = `${appName}.app`;
  const appDir = path.join(stagingDir, bundleName);
  const contentsDir = path.join(appDir, 'Contents');
  const macosDir = path.join(contentsDir, 'MacOS');
  const resourcesDir = path.join(contentsDir, 'Resources');

  fs.mkdirSync(macosDir, { recursive: true });
  fs.mkdirSync(resourcesDir, { recursive: true });

  logFn(`Creating ${bundleName} bundle...`);
  fs.writeFileSync(path.join(contentsDir, 'Info.plist'), generateInfoPlist(project), 'utf-8');
  logFn('Generated Info.plist');

  if (project.files?.length) {
    const entries = project.files.map(e => ({
      source: resolveVariables(e.source, project),
      dest: e.dest.replace(/\{app\}/g, '').replace(/^[/\\]+/, '') || '.',
    }));
    copyFiles(entries, macosDir);
    logFn(`Copied ${project.files.length} file(s) to Contents/MacOS/`);
  }

  if (project.icon && fs.existsSync(project.icon)) {
    fs.copyFileSync(project.icon, path.join(resourcesDir, path.basename(project.icon)));
    logFn('Copied icon to Contents/Resources/');
  }

  const frameworksDir = path.join(contentsDir, 'Frameworks');
  fs.mkdirSync(frameworksDir, { recursive: true });
  const internalDir = path.join(macosDir, '_internal');
  if (fs.existsSync(internalDir)) {
    for (const name of fs.readdirSync(internalDir)) {
      if (name === 'Python' || /^libpython3\.\d+.*\.dylib$/.test(name)) {
        const src = path.join(internalDir, name);
        const dest = path.join(frameworksDir, name);
        fs.renameSync(src, dest);
        fs.symlinkSync(dest, src);
        logFn(`Moved ${name} to Contents/Frameworks/`);
      }
    }
  }

  const executablePath = path.join(macosDir, project.macos.executable);
  if (fs.existsSync(executablePath)) {
    try { fs.chmodSync(executablePath, 0o755); logFn('Set execute permission'); }
    catch { logFn('Note: Could not set execute permission (cross-compiling)'); }
  }

  const base = `${sanitizeFilename(appName)}-${project.appVersion}-macos`;

  if (process.platform === 'darwin') {
    try {
      await execFileAsync('xattr', ['-cr', appDir]);
      logFn('Cleared quarantine attributes');
    } catch { /* non-fatal */ }

    logFn('Ad-hoc signing app bundle (inside-out)...');
    try {
      const { stdout: foundFiles } = await execFileAsync('find', [
        appDir, '-type', 'f', '(',
        '-name', '*.dylib', '-o', '-name', '*.so', '-o', '-name', '*.pyd',
        ')']);
      const files = foundFiles.trim().split('\n').filter(Boolean);

      for (const f of files) {
        try { await execFileAsync('codesign', ['--remove-signature', f]); } catch { /* ok */ }
      }
      logFn(`Stripped existing signatures from ${files.length} binaries`);

      for (const f of files) {
        await execFileAsync('codesign', ['--force', '-s', '-', f]);
      }
      logFn(`Re-signed ${files.length} binaries`);

      if (fs.existsSync(executablePath)) {
        try { await execFileAsync('codesign', ['--remove-signature', executablePath]); } catch { /* ok */ }
        await execFileAsync('codesign', ['--force', '-s', '-', executablePath]);
        logFn('Signed main executable');
      }

      await execFileAsync('codesign', ['--force', '-s', '-', appDir]);
      logFn('Signed app bundle');
    } catch (e) {
      logFn(`Note: Ad-hoc signing failed (${e.message})`);
    }

    const dmgPath = path.join(outputDir, `${base}.dmg`);
    logFn('Creating .dmg with hdiutil...');

    // Create a temporary DMG staging folder with the app + Applications symlink
    const dmgStaging = path.join(stagingDir, '_dmg_contents');
    fs.mkdirSync(dmgStaging, { recursive: true });

    // Move the .app bundle into the DMG staging area
    const dmgApp = path.join(dmgStaging, bundleName);
    fs.renameSync(appDir, dmgApp);

    // Create an Applications symlink so users can drag-to-install
    try {
      fs.symlinkSync('/Applications', path.join(dmgStaging, 'Applications'));
      logFn('Added Applications symlink for drag-to-install');
    } catch { /* may fail on some systems */ }

    await execFileAsync('hdiutil', [
      'create', '-volname', appName,
      '-srcfolder', dmgStaging,
      '-ov', '-format', 'UDZO',
      dmgPath,
    ]);

    logFn(`Created: ${dmgPath}`);
    return dmgPath;
  } else {
    const tarPath = path.join(outputDir, `${base}.tar.gz`);
    logFn('Creating .tar.gz (not on macOS, .dmg requires hdiutil)...');
    createTarGz(stagingDir, tarPath);
    logFn(`Created: ${tarPath}`);
    return tarPath;
  }
}

// ─── Linux Builder (.deb) ───────────────────────────────────────────────────

function getDirSize(dir) {
  let size = 0;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) size += getDirSize(full);
    else size += fs.statSync(full).size;
  }
  return size;
}

async function buildLinux(project, stagingDir, outputDir, logFn) {
  const appName = project.appName;
  const pkgName = sanitizeFilename(appName);
  let installDir = resolveVariables(project.linux.installDir || '/opt/{appName}', project);
  installDir = installDir.replace(/\\/g, '/');
  const executable = project.linux.executable;

  // Data tree
  const dataDir = path.join(stagingDir, 'data');
  const appInstallDir = path.join(dataDir, installDir.replace(/^\//, ''));
  const desktopDir = path.join(dataDir, 'usr', 'share', 'applications');
  fs.mkdirSync(appInstallDir, { recursive: true });
  fs.mkdirSync(desktopDir, { recursive: true });

  logFn('Copying files...');
  copyFiles(project.files, appInstallDir);

  if (project.icon && fs.existsSync(project.icon)) {
    fs.copyFileSync(project.icon, path.join(appInstallDir, path.basename(project.icon)));
  }

  // .desktop file
  const desktop = [
    '[Desktop Entry]', 'Type=Application',
    `Name=${appName}`, `Exec=${installDir}/${executable}`,
    `Icon=${installDir}/${project.icon ? path.basename(project.icon) : 'icon.png'}`,
    `Categories=${(project.linux.categories || ['Utility']).join(';')};`,
    `Comment=${project.description || ''}`, 'Terminal=false',
  ].join('\n') + '\n';
  fs.writeFileSync(path.join(desktopDir, `${pkgName}.desktop`), desktop);
  logFn('Generated .desktop file');

  // DEBIAN control
  const controlDir = path.join(stagingDir, 'control');
  fs.mkdirSync(controlDir, { recursive: true });
  const installedSize = Math.ceil(getDirSize(dataDir) / 1024);
  const deps = project.linux.dependencies?.length ? project.linux.dependencies.join(', ') : '';
  let control = `Package: ${pkgName}\nVersion: ${project.appVersion}\nSection: ${project.linux.section || 'utils'}\nPriority: ${project.linux.priority || 'optional'}\nArchitecture: amd64\nMaintainer: ${project.linux.maintainer}\nInstalled-Size: ${installedSize}\nDescription: ${project.description || appName}\n`;
  if (deps) control += `Depends: ${deps}\n`;
  if (project.website) control += `Homepage: ${project.website}\n`;
  fs.writeFileSync(path.join(controlDir, 'control'), control);

  // postinst
  let postinst = '#!/bin/bash\n';
  postinst += `chmod +x "${installDir}/${executable}"\n`;
  if (project.installer?.postInstallScript) postinst += project.installer.postInstallScript + '\n';
  fs.writeFileSync(path.join(controlDir, 'postinst'), postinst);

  if (project.installer?.preInstallScript) {
    fs.writeFileSync(path.join(controlDir, 'preinst'), '#!/bin/bash\n' + project.installer.preInstallScript + '\n');
  }

  logFn('Generated control files');

  // Build archives
  const controlTar = path.join(stagingDir, 'control.tar.gz');
  const dataTar = path.join(stagingDir, 'data.tar.gz');
  createTarGz(controlDir, controlTar);
  createTarGz(dataDir, dataTar);

  const debFile = path.join(outputDir, `${pkgName}-${project.appVersion}-amd64.deb`);
  const deb = createArArchive([
    { name: 'debian-binary', data: Buffer.from('2.0\n') },
    { name: 'control.tar.gz', data: fs.readFileSync(controlTar) },
    { name: 'data.tar.gz', data: fs.readFileSync(dataTar) },
  ]);
  fs.writeFileSync(debFile, deb);
  logFn(`Created: ${debFile}`);
  return debFile;
}

// ─── Main CLI ───────────────────────────────────────────────────────────────

const BUILDERS = { windows: buildWindows, macos: buildMacOS, linux: buildLinux };

async function build(projectPath, platforms, outputDir) {
  const absPath = path.resolve(projectPath);
  if (!fs.existsSync(absPath)) { console.error(`File not found: ${absPath}`); process.exit(1); }

  const project = JSON.parse(fs.readFileSync(absPath, 'utf-8'));
  console.log(`\n  Multi-Platform Setup Compiler (CLI)\n`);
  console.log(`  Project:   ${project.appName} ${project.appVersion}`);
  console.log(`  Platforms: ${platforms.join(', ')}`);
  console.log(`  Host OS:   ${process.platform}\n`);

  const errors = validateProject(project, platforms);
  if (errors.length) {
    for (const e of errors) log('error', e.message, e.platform);
    process.exit(1);
  }

  const out = outputDir || path.join(path.dirname(absPath), 'mpsc-output', project.appName);
  fs.mkdirSync(out, { recursive: true });
  console.log(`  Output:    ${out}\n`);

  const tmpBase = path.join(os.tmpdir(), `mpsc-build-${Date.now()}`);
  fs.mkdirSync(tmpBase, { recursive: true });

  const results = [];
  for (const platform of platforms) {
    const start = Date.now();
    log('info', `Building ${platform}...`, platform);
    const staging = path.join(tmpBase, platform);
    fs.mkdirSync(staging, { recursive: true });
    try {
      const outPath = await BUILDERS[platform](project, staging, out, (msg) => log('info', msg, platform));
      const dur = ((Date.now() - start) / 1000).toFixed(1);
      log('success', `Done in ${dur}s -> ${outPath}`, platform);
      results.push({ platform, success: true });
    } catch (err) {
      log('error', `Failed: ${err.message || err}`, platform);
      results.push({ platform, success: false });
    }
  }

  try { fs.rmSync(tmpBase, { recursive: true, force: true }); } catch {}

  const ok = results.filter(r => r.success).length;
  const fail = results.filter(r => !r.success).length;
  console.log(`\n  Build complete: ${ok} succeeded, ${fail} failed\n`);
  if (fail > 0) process.exit(1);
}

// ─── CLI argument parsing ───────────────────────────────────────────────────

const args = process.argv.slice(2);

if (args[0] !== 'build' || args.length < 2) {
  console.log(`
  MPSC CLI - Multi-Platform Setup Compiler

  Usage:
    node cli.mjs build <project.mpsc> [options]

  Options:
    --platform <name>   Target platform(s): windows, macos, linux
                        Can be specified multiple times. Default: all.
    --output <dir>      Output directory. Default: ./mpsc-output/<appName>

  Examples:
    node cli.mjs build myapp.mpsc
    node cli.mjs build myapp.mpsc --platform macos
    node cli.mjs build myapp.mpsc --platform windows --platform linux
    node cli.mjs build myapp.mpsc --platform macos --output ./installers
  `);
  process.exit(0);
}

const projectFile = args[1];
let platforms = [];
let outputDir = null;

for (let i = 2; i < args.length; i++) {
  if (args[i] === '--platform' && args[i + 1]) { platforms.push(args[++i]); }
  else if (args[i] === '--output' && args[i + 1]) { outputDir = args[++i]; }
}

if (platforms.length === 0) platforms = ['windows', 'macos', 'linux'];

for (const p of platforms) {
  if (!BUILDERS[p]) { console.error(`Unknown platform: ${p}. Use: windows, macos, linux`); process.exit(1); }
}

build(projectFile, platforms, outputDir).catch(err => { console.error(err); process.exit(1); });
