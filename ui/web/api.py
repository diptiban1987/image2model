from fastapi import FastAPI, UploadFile, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse, Response
import shutil
import os
import re
import platform
import psutil
from pathlib import Path
from typing import Optional
from core.unified_pipeline import run_pipeline_async, get_available_models, validate_api_token, resolve_hitem3d_credentials, save_hitem3d_credentials
from core.hitem3d_api import InsufficientBalanceError
from core.auth import (
    is_password_configured,
    verify_password,
    verify_session_token,
    create_session_token,
)

app = FastAPI()

OUTPUT_DIR = Path("output").resolve()
SESSION_COOKIE = "imagetoad_session"
SESSION_MAX_AGE = 24 * 3600

def _get_session(request: Request) -> Optional[str]:
    return request.cookies.get(SESSION_COOKIE)


async def require_session(request: Request) -> bool:
    """Dependency: require valid session when password is configured. Raises 401 otherwise."""
    if not is_password_configured():
        return True
    token = _get_session(request)
    if verify_session_token(token or ""):
        return True
    raise HTTPException(status_code=401, detail="Authentication required")


def _main_app_html():
    """Return the main app HTML (used by index when authenticated)."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <title>Image to 3D Converter</title>
        <style>
            body {
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                background: radial-gradient(circle at top, #1e293b, #020617);
                color: #e5e7eb;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
            }
            .card {
                background: rgba(15, 23, 42, 0.95);
                border-radius: 16px;
                padding: 24px 28px;
                box-shadow: 0 24px 60px rgba(15, 23, 42, 0.8);
                width: 100%;
                max-width: 520px;
                border: 1px solid rgba(148, 163, 184, 0.25);
            }
            h1 {
                margin: 0 0 6px;
                font-size: 24px;
            }
            p {
                margin: 0 0 18px;
                color: #9ca3af;
            }
            .dropzone {
                border: 1px dashed #4b5563;
                border-radius: 12px;
                padding: 20px;
                text-align: center;
                cursor: pointer;
                background: rgba(15,23,42,0.6);
                transition: border-color 0.15s ease, background 0.15s ease;
            }
            .dropzone.dragover {
                border-color: #22c55e;
                background: rgba(21,128,61,0.15);
            }
            input[type="file"] {
                display: none;
            }
            button {
                margin-top: 18px;
                width: 100%;
                padding: 10px 16px;
                border-radius: 999px;
                border: none;
                background: linear-gradient(135deg, #22c55e, #16a34a);
                color: white;
                font-weight: 600;
                font-size: 15px;
                cursor: pointer;
                box-shadow: 0 12px 30px rgba(22,163,74,0.45);
                transition: transform 0.08s ease, box-shadow 0.08s ease, filter 0.1s ease;
            }
            button:hover {
                filter: brightness(1.05);
                box-shadow: 0 16px 40px rgba(22,163,74,0.6);
            }
            button:active {
                transform: translateY(1px);
                box-shadow: 0 10px 22px rgba(22,163,74,0.45);
            }
            button:disabled {
                opacity: 0.6;
                cursor: not-allowed;
                box-shadow: none;
            }
            .status {
                margin-top: 14px;
                font-size: 13px;
                color: #9ca3af;
            }
            .status strong {
                color: #e5e7eb;
            }
            .results {
                margin-top: 16px;
                padding-top: 12px;
                border-top: 1px solid rgba(55, 65, 81, 0.9);
                font-size: 13px;
            }
            .results a {
                color: #22c55e;
                text-decoration: none;
            }
            .results a:hover {
                text-decoration: underline;
            }
            .preview {
                margin-top: 14px;
            }
            .preview-label {
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: #6b7280;
            }
            .preview img {
                display: block;
                margin-top: 6px;
                max-width: 100%;
                max-height: 260px;
                border-radius: 12px;
                border: 1px solid rgba(55,65,81,0.8);
                object-fit: contain;
                background: radial-gradient(circle at top, #020617, #020617);
            }
            .badge {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 3px 10px;
                border-radius: 999px;
                background: rgba(15,23,42,1);
                border: 1px solid rgba(55,65,81,0.9);
                font-size: 11px;
                color: #9ca3af;
                margin-bottom: 10px;
            }
            .badge-dot {
                width: 7px;
                height: 7px;
                border-radius: 999px;
                background: #22c55e;
                box-shadow: 0 0 0 4px rgba(34,197,94,0.35);
            }
            /* New styles for processing options */
            .processing-options {
                margin-top: 16px;
                padding: 16px;
                background: rgba(15,23,42,0.8);
                border-radius: 12px;
                border: 1px solid rgba(55,65,81,0.5);
            }
            .option-group {
                margin-bottom: 12px;
            }
            .option-group:last-child {
                margin-bottom: 0;
            }
            .option-label {
                display: block;
                margin-bottom: 6px;
                font-size: 13px;
                font-weight: 500;
                color: #e5e7eb;
            }
            .radio-group {
                display: flex;
                gap: 16px;
                margin-bottom: 8px;
            }
            .radio-option {
                display: flex;
                align-items: center;
                gap: 6px;
            }
            input[type="radio"] {
                accent-color: #22c55e;
            }
            select, input[type="text"] {
                width: 100%;
                padding: 8px 12px;
                border: 1px solid rgba(55,65,81,0.8);
                border-radius: 8px;
                background: rgba(15,23,42,0.9);
                color: #e5e7eb;
                font-size: 13px;
            }
            select:focus, input[type="text"]:focus {
                outline: none;
                border-color: #22c55e;
                box-shadow: 0 0 0 2px rgba(34,197,94,0.2);
            }
            .api-options {
                display: none;
                margin-top: 12px;
                padding-top: 12px;
                border-top: 1px solid rgba(55,65,81,0.5);
            }
            .api-options.active {
                display: block;
            }
            .local-options {
                margin-top: 8px;
            }
            .local-options .option-group {
                margin-bottom: 0;
            }
            .download-links {
                margin-top: 8px;
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
            }
            .download-links a {
                display: inline-block;
                padding: 6px 12px;
                border-radius: 8px;
                background: rgba(34,197,94,0.2);
                color: #22c55e;
                text-decoration: none;
                font-size: 13px;
            }
            .download-links a:hover {
                background: rgba(34,197,94,0.35);
            }
            .model-info {
                margin-top: 8px;
                padding: 8px 12px;
                background: rgba(21,128,61,0.1);
                border-left: 3px solid #22c55e;
                border-radius: 4px;
                font-size: 12px;
                color: #a7f3d0;
            }
            .warning-box {
                margin-top: 10px;
                padding: 8px 12px;
                background: rgba(251, 191, 36, 0.12);
                border-left: 3px solid #f59e0b;
                border-radius: 4px;
                font-size: 12px;
                color: #fcd34d;
            }
            .error-box {
                margin-top: 10px;
                padding: 8px 12px;
                background: rgba(127, 29, 29, 0.2);
                border-left: 3px solid #ef4444;
                border-radius: 4px;
                font-size: 12px;
                color: #fecdd3;
            }
            .system-panel {
                margin-top: 16px;
                padding: 14px;
                border-radius: 14px;
                background: linear-gradient(135deg, rgba(15,23,42,0.95), rgba(2,6,23,0.85));
                border: 1px solid rgba(55,65,81,0.7);
                box-shadow: inset 0 0 0 1px rgba(148,163,184,0.06);
            }
            .system-title {
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: #94a3b8;
                margin-bottom: 10px;
            }
            .system-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 10px;
                font-size: 12px;
                color: #cbd5f5;
            }
            .system-item {
                background: rgba(15,23,42,0.7);
                border: 1px solid rgba(55,65,81,0.6);
                border-radius: 10px;
                padding: 8px 10px;
            }
            .system-item span {
                display: block;
                font-size: 10px;
                color: #94a3b8;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                margin-bottom: 4px;
            }
            .requirements {
                margin-top: 10px;
                font-size: 12px;
                color: #9ca3af;
                line-height: 1.4;
            }
            .progress-wrap {
                margin-top: 14px;
                padding: 10px 12px;
                border-radius: 12px;
                background: rgba(15,23,42,0.8);
                border: 1px solid rgba(55,65,81,0.6);
            }
            .progress-bar {
                width: 100%;
                height: 8px;
                border-radius: 999px;
                background: rgba(30,41,59,0.9);
                overflow: hidden;
                margin: 8px 0 6px;
            }
            .progress-fill {
                height: 100%;
                width: 0%;
                background: linear-gradient(90deg, #22c55e, #38bdf8);
                box-shadow: 0 0 12px rgba(56,189,248,0.5);
                transition: width 0.3s ease;
            }
            .progress-meta {
                display: flex;
                justify-content: space-between;
                font-size: 12px;
                color: #cbd5f5;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <div class="badge">
                    <span class="badge-dot"></span>
                    <span>Image → 3D model pipeline</span>
                </div>
                <a href="/logout" style="color:#94a3b8; font-size:13px; text-decoration:none;">Log out</a>
            </div>
            <h1>Image to 3D Converter</h1>
            <p>Select a single image and generate downloadable 3D files (<code>.obj</code>, <code>.stl</code>, <code>.glb</code>).</p>
            <p>Resolutions: 512³, 1024³, 1536³, and 1536³ Pro. Output Formats: OBJ, GLB, STL, FBX, USDZ.</p>
            
            <label class="dropzone" id="dropzone">
                <input id="fileInput" type="file" accept="image/*" />
                <div id="dropText">Click to choose an image or drop it here</div>
            </label>
            
            <div class="preview" id="previewContainer" style="display:none;">
                <div class="preview-label">Preview</div>
                <img id="previewImage" alt="Selected image preview" />
            </div>
            
            <!-- Processing Options -->
            <div class="processing-options">
                <div class="option-group">
                    <label class="option-label">Processing Method</label>
                    <div class="radio-group">
                        <div class="radio-option">
                            <input type="radio" id="local" name="processing" value="local" checked>
                            <label for="local">Local Processing</label>
                        </div>
                        <div class="radio-option">
                            <input type="radio" id="api" name="processing" value="api">
                            <label for="api">Hitem3D API</label>
                        </div>
                    </div>
                </div>
                
                <div class="local-options" id="localOptions">
                    <div class="option-group">
                        <label class="option-label" for="quality">Mesh quality (local)</label>
                        <select id="quality">
                            <option value="draft">Draft (fast)</option>
                            <option value="standard" selected>Standard</option>
                            <option value="high">High</option>
                            <option value="production">Production</option>
                        </select>
                    </div>
                </div>
                
                <div class="api-options" id="apiOptions">
                    <div class="option-group">
                        <label class="option-label" for="apiToken">API Token</label>
                        <input type="text" id="apiToken" placeholder="Enter your Hitem3D API token">
                    </div>

                    <div class="option-group">
                        <label class="option-label" for="serverApiToken">Server API Token (shared)</label>
                        <input type="text" id="serverApiToken" placeholder="Paste token to save for all users">
                        <button id="saveServerToken" type="button" style="margin-top:8px; width:100%;">Save Server Token</button>
                    </div>
                    
                    <div class="option-group">
                        <label class="option-label" for="apiModel">Model</label>
                        <select id="apiModel">
                            <option value="hitem3dv1.5">HiTeM3D v1.5</option>
                            <option value="hitem3dv2.0">HiTeM3D v2.0</option>
                            <option value="scene-portraitv1.5">Scene Portrait v1.5</option>
                            <option value="scene-portraitv2.0">Scene Portrait v2.0</option>
                            <option value="scene-portraitv2.1">Scene Portrait v2.1</option>
                        </select>
                        <div class="model-info" id="modelInfo">
                            General purpose 3D generation model. Recommended resolution: 1024
                        </div>
                    </div>
                    
                    <div class="option-group">
                        <label class="option-label" for="apiResolution">Resolution</label>
                        <select id="apiResolution">
                            <option value="512">512³</option>
                            <option value="1024" selected>1024³</option>
                            <option value="1536">1536³</option>
                            <option value="1536pro">1536³ Pro</option>
                        </select>
                    </div>

                    <div class="option-group">
                        <label class="option-label" for="apiFormat">Output Format</label>
                        <select id="apiFormat">
                            <option value="obj" selected>OBJ</option>
                            <option value="glb">GLB</option>
                            <option value="stl">STL</option>
                            <option value="fbx">FBX</option>
                            <option value="usdz">USDZ</option>
                        </select>
                    </div>
                </div>
            </div>

            <div class="system-panel" id="systemPanel">
                <div class="system-title">System & Requirements</div>
                <div class="system-grid">
                    <div class="system-item"><span>Available RAM</span><div id="sysAvailable">--</div></div>
                    <div class="system-item"><span>Total RAM</span><div id="sysTotal">--</div></div>
                    <div class="system-item"><span>Required RAM</span><div id="sysRequired">--</div></div>
                    <div class="system-item"><span>CPU Cores</span><div id="sysCpu">--</div></div>
                    <div class="system-item"><span>Platform</span><div id="sysPlatform">--</div></div>
                    <div class="system-item"><span>Mode</span><div id="sysMode">Local</div></div>
                </div>
                <div class="requirements" id="requirementsText">
                    Local processing runs TripoSR on CPU. Keep at least 6GB RAM available for stable results.
                </div>
                <div class="progress-wrap" id="progressSection" style="display:none;">
                    <div style="font-size:12px; color:#e5e7eb;">Processing progress</div>
                    <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
                    <div class="progress-meta">
                        <div id="progressPercent">0%</div>
                        <div id="progressEta">ETA --:--</div>
                        <div id="progressElapsed">Elapsed 00:00</div>
                    </div>
                </div>
            </div>
            
            <button id="generateBtn" disabled>Choose an image to start</button>
            <div class="status" id="status"></div>
            <div class="results" id="results"></div>
        </div>

        <script>
            const fileInput = document.getElementById('fileInput');
            const dropzone = document.getElementById('dropzone');
            const dropText = document.getElementById('dropText');
            const btn = document.getElementById('generateBtn');
            const statusEl = document.getElementById('status');
            const resultsEl = document.getElementById('results');
            const previewContainer = document.getElementById('previewContainer');
            const previewImage = document.getElementById('previewImage');
            const processingRadios = document.querySelectorAll('input[name="processing"]');
            const apiOptions = document.getElementById('apiOptions');
            const apiModel = document.getElementById('apiModel');
            const modelInfo = document.getElementById('modelInfo');
            const apiToken = document.getElementById('apiToken');
            const serverApiToken = document.getElementById('serverApiToken');
            const saveServerToken = document.getElementById('saveServerToken');
            const apiResolution = document.getElementById('apiResolution');
            const apiFormat = document.getElementById('apiFormat');
            const sysAvailable = document.getElementById('sysAvailable');
            const sysTotal = document.getElementById('sysTotal');
            const sysRequired = document.getElementById('sysRequired');
            const sysCpu = document.getElementById('sysCpu');
            const sysPlatform = document.getElementById('sysPlatform');
            const sysMode = document.getElementById('sysMode');
            const requirementsText = document.getElementById('requirementsText');
            const progressSection = document.getElementById('progressSection');
            const progressFill = document.getElementById('progressFill');
            const progressPercent = document.getElementById('progressPercent');
            const progressEta = document.getElementById('progressEta');
            const progressElapsed = document.getElementById('progressElapsed');
            let serverHasCredentials = false;
            let lastTotalSeconds = null;
            let progressTimer = null;
            let progressStart = null;
            let progressExpected = null;
            let lastSystemInfo = null;
            
            let previewUrl = null;

            // Model information
            const modelDescriptions = {
                'hitem3dv1.5': {
                    description: 'General purpose 3D generation model. Recommended resolution: 1024',
                    resolutions: ['512', '1024', '1536', '1536pro']
                },
                'hitem3dv2.0': {
                    description: 'Enhanced 3D generation model with better quality. Recommended resolution: 1536',
                    resolutions: ['1536', '1536pro']
                },
                'scene-portraitv1.5': {
                    description: 'Specialized portrait model. Recommended resolution: 1536',
                    resolutions: ['1536']
                },
                'scene-portraitv2.0': {
                    description: 'Specialized portrait model. Recommended resolution: 1536pro',
                    resolutions: ['1536pro']
                },
                'scene-portraitv2.1': {
                    description: 'Specialized portrait model. Recommended resolution: 1536pro',
                    resolutions: ['1536pro']
                }
            };

            function setStatus(text) {
                statusEl.textContent = text || '';
            }

            function updateApiTokenPlaceholder() {
                apiToken.placeholder = serverHasCredentials ? 'Using server credentials (optional)' : 'Enter your Hitem3D API token';
            }

            function formatTime(totalSeconds) {
                const seconds = Math.max(0, Math.round(totalSeconds || 0));
                const minutes = Math.floor(seconds / 60);
                const rem = seconds % 60;
                return `${String(minutes).padStart(2, '0')}:${String(rem).padStart(2, '0')}`;
            }

            function updateProgress(elapsedSeconds) {
                const expected = progressExpected || 0;
                let percent = expected > 0 ? (elapsedSeconds / expected) * 100 : 0;
                percent = Math.max(0, Math.min(95, percent));
                progressFill.style.width = `${percent.toFixed(1)}%`;
                progressPercent.textContent = `${percent.toFixed(1)}%`;
                progressElapsed.textContent = `Elapsed ${formatTime(elapsedSeconds)}`;
                const remaining = expected > 0 ? Math.max(0, expected - elapsedSeconds) : 0;
                progressEta.textContent = `ETA ${formatTime(remaining)}`;
            }

            function startProgress(useApi) {
                progressStart = Date.now();
                progressExpected = lastTotalSeconds || (useApi ? 120 : 180);
                progressSection.style.display = 'block';
                updateProgress(0);
                if (progressTimer) clearInterval(progressTimer);
                progressTimer = setInterval(() => {
                    const elapsed = (Date.now() - progressStart) / 1000;
                    updateProgress(elapsed);
                }, 500);
            }

            function stopProgress(success) {
                if (progressTimer) {
                    clearInterval(progressTimer);
                    progressTimer = null;
                }
                if (success) {
                    progressFill.style.width = '100%';
                    progressPercent.textContent = '100%';
                    progressEta.textContent = 'ETA 00:00';
                } else {
                    progressFill.style.width = '0%';
                    progressPercent.textContent = '0%';
                    progressEta.textContent = 'ETA --:--';
                }
            }

            function setResults(data) {
                resultsEl.innerHTML = '';
                if (!data) return;
                const { obj, stl, glb, fbx, usdz, obj_url, stl_url, glb_url, fbx_url, usdz_url, stats, processing_method, api_model, api_format, quality, warning, system_info, error_message } = data;
                const lines = [];
                
                if (error_message) {
                    lines.push(`<div class="error-box"><strong>Error:</strong> ${error_message}</div>`);
                }
                if (processing_method) {
                    lines.push(`<div><strong>Method:</strong> ${processing_method === 'local' ? 'Local Processing' : 'Hitem3D API'}</div>`);
                }
                if (api_model) {
                    lines.push(`<div><strong>Model:</strong> ${api_model}</div>`);
                }
                if (api_format) {
                    lines.push(`<div><strong>Format:</strong> ${api_format.toUpperCase()}</div>`);
                }
                if (quality) {
                    lines.push(`<div><strong>Quality:</strong> ${quality}</div>`);
                }
                if (warning) {
                    lines.push(`<div class="warning-box"><strong>Warning:</strong> ${warning}</div>`);
                }
                if (system_info && processing_method === 'local') {
                    lines.push(
                        `<div style="margin-top:8px;"><strong>System:</strong> ${system_info.platform || 'unknown'}</div>`
                    );
                    lines.push(
                        `<div><strong>CPU:</strong> ${system_info.cpu_count || 'unknown'}</div>`
                    );
                    const total = system_info.ram_total_gb ?? 'unknown';
                    const free = system_info.ram_available_gb ?? 'unknown';
                    const req = system_info.ram_required_gb ?? 8;
                    lines.push(
                        `<div><strong>RAM:</strong> ${free}GB free / ${total}GB total (required ${req}GB)</div>`
                    );
                }
                
                if (obj) lines.push(`<div><strong>OBJ:</strong> <code>${obj}</code></div>`);
                if (stl) lines.push(`<div><strong>STL:</strong> <code>${stl}</code></div>`);
                if (glb) lines.push(`<div><strong>GLB:</strong> <code>${glb}</code></div>`);
                if (fbx) lines.push(`<div><strong>FBX:</strong> <code>${fbx}</code></div>`);
                if (usdz) lines.push(`<div><strong>USDZ:</strong> <code>${usdz}</code></div>`);
                
                const downloads = [];
                if (obj_url) downloads.push(`<a href="${obj_url}" download>Download OBJ</a>`);
                if (stl_url) downloads.push(`<a href="${stl_url}" download>Download STL</a>`);
                if (glb_url) downloads.push(`<a href="${glb_url}" download>Download GLB</a>`);
                if (fbx_url) downloads.push(`<a href="${fbx_url}" download>Download FBX</a>`);
                if (usdz_url) downloads.push(`<a href="${usdz_url}" download>Download USDZ</a>`);
                if (downloads.length) {
                    lines.push('<div class="download-links">' + downloads.join('') + '</div>');
                }

                if (stats && typeof stats === 'object') {
                    const total = typeof stats.total_seconds === 'number'
                        ? stats.total_seconds.toFixed(3)
                        : null;
                    const stages = stats.stages && typeof stats.stages === 'object'
                        ? stats.stages
                        : null;

                    if (total !== null) {
                        lines.push(`<div style="margin-top:10px;"><strong>Total time:</strong> ${total}s</div>`);
                        if (typeof stats.total_seconds === 'number') {
                            lastTotalSeconds = Math.max(1, stats.total_seconds);
                        }
                    }
                    if (stages) {
                        lines.push('<div style="margin-top:4px;"><strong>Stages:</strong></div>');
                        lines.push('<ul style="margin:4px 0 0 16px; padding:0; font-size:12px;">' +
                            Object.entries(stages)
                                .map(([k, v]) => {
                                    const val = typeof v === 'number' ? v.toFixed(3) : v;
                                    return `<li>${k}: ${val}s</li>`;
                                }).join('') +
                            '</ul>');
                    }
                }

                resultsEl.innerHTML = lines.join('');
            }

            function showPreview(file) {
                if (!file || !file.type.startsWith('image/')) {
                    previewContainer.style.display = 'none';
                    if (previewUrl) {
                        URL.revokeObjectURL(previewUrl);
                        previewUrl = null;
                    }
                    return;
                }
                if (previewUrl) {
                    URL.revokeObjectURL(previewUrl);
                }
                previewUrl = URL.createObjectURL(file);
                previewImage.src = previewUrl;
                previewContainer.style.display = 'block';
            }

            function updateButtonLabel() {
                if (fileInput.files.length > 0) {
                    const name = fileInput.files[0].name;
                    dropText.textContent = name;
                    btn.textContent = 'Generate 3D model';
                    btn.disabled = false;
                    showPreview(fileInput.files[0]);
                } else {
                    dropText.textContent = 'Click to choose an image or drop it here';
                    btn.textContent = 'Choose an image to start';
                    btn.disabled = true;
                    showPreview(null);
                }
            }

            function updateApiOptions() {
                const useApi = document.querySelector('input[name="processing"]:checked').value === 'api';
                apiOptions.classList.toggle('active', useApi);
                const placeholder = serverHasCredentials ? 'Using server credentials' : 'Enter your Hitem3D API token';
                apiToken.placeholder = placeholder;
                sysMode.textContent = useApi ? 'API' : 'Local';
                requirementsText.textContent = useApi
                    ? 'Cloud processing uses the Hitem3D API. Network stability improves completion time.'
                    : 'Local processing runs TripoSR on CPU. Keep at least 6GB RAM available for stable results.';
                updateModelInfo();
            }

            function updateModelInfo() {
                const model = apiModel.value;
                const info = modelDescriptions[model];
                if (info) {
                    modelInfo.textContent = info.description;
                    
                    // Update resolution options
                    const currentResolution = apiResolution.value;
                    apiResolution.innerHTML = '';
                    info.resolutions.forEach(res => {
                        const option = document.createElement('option');
                        option.value = res;
                        option.textContent = res === '1536pro' ? '1536³ Pro' : `${res}³`;
                        if (res === currentResolution || (res === info.resolutions[0] && !info.resolutions.includes(currentResolution))) {
                            option.selected = true;
                        }
                        apiResolution.appendChild(option);
                    });
                }
            }

            // Event listeners
            processingRadios.forEach(radio => {
                radio.addEventListener('change', updateApiOptions);
            });
            
            saveServerToken.addEventListener('click', async () => {
                const token = serverApiToken.value.trim();
                if (!token) {
                    setStatus('Please paste a server API token first.');
                    return;
                }
                saveServerToken.disabled = true;
                try {
                    const form = new FormData();
                    form.append('token', token);
                    const resp = await fetch('/credentials/update', {
                        method: 'POST',
                        body: form,
                        credentials: 'same-origin'
                    });
                    if (!resp.ok) {
                        const err = await resp.json();
                        throw new Error(err.detail || `Server returned ${resp.status}`);
                    }
                    serverHasCredentials = true;
                    serverApiToken.value = '';
                    updateApiTokenPlaceholder();
                    setStatus('Server API token saved.');
                } catch (e) {
                    setStatus(`Error: ${e.message}`);
                } finally {
                    saveServerToken.disabled = false;
                }
            });
            
            apiModel.addEventListener('change', updateModelInfo);

            dropzone.addEventListener('click', () => fileInput.click());

            fileInput.addEventListener('change', () => {
                updateButtonLabel();
                setStatus('');
                setResults(null);
            });

            ;['dragenter', 'dragover'].forEach(evt => {
                dropzone.addEventListener(evt, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    dropzone.classList.add('dragover');
                });
            });

            ;['dragleave', 'drop'].forEach(evt => {
                dropzone.addEventListener(evt, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (evt === 'drop') return;
                    dropzone.classList.remove('dragover');
                });
            });

            dropzone.addEventListener('drop', (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove('dragover');
                const files = e.dataTransfer.files;
                if (files && files.length > 0) {
                    fileInput.files = files;
                    updateButtonLabel();
                    setStatus('');
                    setResults(null);
                }
            });

            btn.addEventListener('click', async () => {
                if (!fileInput.files.length) return;
                const file = fileInput.files[0];

                const form = new FormData();
                form.append('file', file);
                
                const useApi = document.querySelector('input[name="processing"]:checked').value === 'api';
                form.append('use_api', useApi);
                
                if (!useApi) {
                    form.append('quality', document.getElementById('quality').value);
                }
                
                if (useApi) {
                    const token = apiToken.value.trim();
                    if (!serverHasCredentials && !token) {
                        setStatus('Please enter your Hitem3D API token');
                        return;
                    }
                    if (token) {
                        form.append('api_token', token);
                    }
                    const model = apiModel.value;
                    const allowed = modelDescriptions[model]?.resolutions || [];
                    if (allowed.length && !allowed.includes(apiResolution.value)) {
                        apiResolution.value = allowed[0];
                    }
                    form.append('api_model', apiModel.value);
                    form.append('api_resolution', apiResolution.value);
                    form.append('api_format', apiFormat.value);
                }

                btn.disabled = true;
                btn.textContent = 'Processing...';
                setResults(null);
                let preStatus = useApi ? 'Uploading to Hitem3D API and generating 3D model...' : 'Processing locally...';
                if (!useApi && lastSystemInfo && typeof lastSystemInfo.available_gb === 'number' && typeof lastSystemInfo.required_gb === 'number') {
                    if (lastSystemInfo.available_gb < lastSystemInfo.required_gb) {
                        preStatus = `Warning: Low available RAM (${lastSystemInfo.available_gb}GB available, ${lastSystemInfo.required_gb}GB required). Processing locally...`;
                    }
                }
                setStatus(preStatus);
                startProgress(useApi);

                async function readResponseJson(resp) {
                    const text = await resp.text();
                    if (!text) return null;
                    try {
                        return JSON.parse(text);
                    } catch (e) {
                        return { error_message: text };
                    }
                }

                try {
                    const resp = await fetch('/generate', {
                        method: 'POST',
                        body: form,
                        credentials: 'same-origin'
                    });
                    if (!resp.ok) {
                        const error = await readResponseJson(resp);
                        const detail = error && (error.detail || error.error || error.error_message);
                        throw new Error(detail || `Server returned ${resp.status}`);
                    }
                    const data = await readResponseJson(resp) || {};
                    const errorMsg = data.error_message || data.error || '';
                    if (errorMsg) {
                        setStatus(`Error: ${errorMsg}`);
                        if (!data.error_message) {
                            data.error_message = errorMsg;
                        }
                        stopProgress(false);
                    } else {
                        setStatus('Done! 3D files generated successfully.');
                        stopProgress(true);
                    }
                    setResults(data);
                } catch (err) {
                    console.error(err);
                    const msg = err && err.message ? err.message : 'Request failed';
                    const friendly = msg === 'Failed to fetch'
                        ? 'Failed to fetch. The server may have restarted or become unreachable during processing.'
                        : msg;
                    setStatus(`Error: ${friendly}`);
                    setResults({ error_message: friendly });
                    stopProgress(false);
                } finally {
                    btn.disabled = false;
                    btn.textContent = 'Generate again';
                }
            });

            // Initialize
            (async () => {
                try {
                    const resp = await fetch('/credentials/availability');
                    if (resp.ok) {
                        const data = await resp.json();
                        serverHasCredentials = !!data.available;
                    }
                } catch (e) {}
                updateApiTokenPlaceholder();
                const refreshSystemInfo = async () => {
                    try {
                        const infoResp = await fetch('/system-info');
                        if (!infoResp.ok) return;
                        const info = await infoResp.json();
                        lastSystemInfo = info;
                        sysAvailable.textContent = info.available_gb !== null ? `${info.available_gb} GB` : '--';
                        sysTotal.textContent = info.total_gb !== null ? `${info.total_gb} GB` : '--';
                        sysRequired.textContent = info.required_gb !== null ? `${info.required_gb} GB` : '--';
                        sysCpu.textContent = info.cpu_count !== null ? info.cpu_count : '--';
                        sysPlatform.textContent = info.platform || '--';
                    } catch (e) {}
                };
                await refreshSystemInfo();
                setInterval(refreshSystemInfo, 3000);
                updateApiOptions();
            })();
        </script>
    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve main app; redirect to login when password is set and session invalid."""
    if is_password_configured() and not verify_session_token(_get_session(request) or ""):
        return RedirectResponse(url="/login")
    return _main_app_html()


@app.get("/system-info")
async def system_info(_auth: bool = Depends(require_session)):
    try:
        mem = psutil.virtual_memory()
        required = 6.0
        return {
            "available_gb": round(mem.available / (1024 ** 3), 2),
            "total_gb": round(mem.total / (1024 ** 3), 2),
            "required_gb": required,
            "cpu_count": os.cpu_count(),
            "platform": platform.platform(),
        }
    except Exception:
        return {
            "available_gb": None,
            "total_gb": None,
            "required_gb": 6.0,
            "cpu_count": None,
            "platform": None,
        }


LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Login — Image to 3D</title>
    <style>
        body { font-family: system-ui, sans-serif; background: #1e293b; color: #e5e7eb; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .card { background: rgba(15,23,42,0.95); border-radius: 16px; padding: 28px; max-width: 360px; width: 100%; border: 1px solid rgba(148,163,184,0.25); }
        h1 { margin: 0 0 8px; font-size: 22px; }
        input { width: 100%; padding: 10px 12px; margin: 8px 0; border: 1px solid #475569; border-radius: 8px; background: #0f172a; color: #e5e7eb; box-sizing: border-box; }
        button { width: 100%; padding: 10px; margin-top: 12px; border: none; border-radius: 8px; background: #22c55e; color: white; font-weight: 600; cursor: pointer; }
        button:hover { filter: brightness(1.05); }
        .error { color: #f87171; font-size: 14px; margin-top: 8px; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Image to 3D — Login</h1>
        <p style="color:#94a3b8; margin:0 0 16px;">Enter the application password.</p>
        <form method="post" action="/login">
            <input type="password" name="password" placeholder="Password" required autofocus />
            <button type="submit">Log in</button>
        </form>
        <p id="err" class="error"></p>
    </div>
    <script>
        const params = new URLSearchParams(location.search);
        if (params.get('error') === '1') document.getElementById('err').textContent = 'Incorrect password.';
    </script>
</body>
</html>
"""


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Serve login form."""
    return LOGIN_HTML


@app.post("/login")
async def login_post(password: str = Form(...)):
    """Verify password (server-side bcrypt) and set session cookie."""
    if not verify_password(password):
        return RedirectResponse(url="/login?error=1", status_code=302)
    token = create_session_token()
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        max_age=SESSION_MAX_AGE,
        samesite="lax",
    )
    return response


@app.get("/logout")
async def logout():
    """Clear session cookie and redirect to login."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.post("/generate")
async def generate(
    request: Request,
    file: UploadFile,
    use_api: bool = Form(False),
    api_token: Optional[str] = Form(None),
    api_model: Optional[str] = Form("hitem3dv1.5"),
    api_resolution: Optional[str] = Form("1024"),
    api_format: Optional[str] = Form("glb"),
    quality: str = Form("standard"),
    _auth: bool = Depends(require_session),
):
    """
    Generate 3D model from image with optional API processing.

    Args:
        file: Uploaded image file
        use_api: Whether to use Hitem3D API
        api_token: Hitem3D API token (required if use_api=True and no server credentials)
        api_model: Hitem3D model to use
        api_resolution: Output resolution
        quality: Local mesh quality: draft, standard, high, production
    """
    if use_api:
        credentials = resolve_hitem3d_credentials(api_token)
        if not (credentials["access_token"] or (credentials["client_id"] and credentials["client_secret"])):
            raise HTTPException(status_code=400, detail="Hitem3D credentials are required when using Hitem3D API")
        # Only validate token when user provided one (skip when using server-side credentials)
        if api_token and api_token.strip():
            if not await validate_api_token(api_token.strip()):
                raise HTTPException(status_code=400, detail="Invalid Hitem3D API credentials")
    else:
        try:
            available_gb = psutil.virtual_memory().available / (1024 ** 3)
            if available_gb < 6:
                raise HTTPException(
                    status_code=400,
                    detail="Local processing requires at least 6GB available RAM. Please upgrade your PC RAM or use Hitem3D API."
                )
        except HTTPException:
            raise
        except Exception:
            pass

    os.makedirs("input", exist_ok=True)
    original_name = Path(file.filename).name
    base_name = os.path.splitext(original_name)[0]
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", base_name).strip("._-") or "model"
    input_path = f"input/{original_name}"

    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        result = await run_pipeline_async(
            input_path,
            name=safe_name,
            use_api=use_api,
            api_token=api_token,
            api_model=api_model,
            api_resolution=api_resolution,
            api_format=api_format,
            quality=quality if quality in ("draft", "standard", "high", "production") else "standard",
        )

        # Add download URLs for web UI (filename only for security)
        base = "/download"
        for key in ("obj", "stl", "glb", "fbx", "usdz"):
            path = result.get(key)
            if path:
                name = Path(path).name
                result[f"{key}_url"] = f"{base}?path={name}" if name else None
            else:
                result[f"{key}_url"] = None
        if result.get("error") and not result.get("error_message"):
            result["error_message"] = result["error"]

        return result

    except InsufficientBalanceError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/credentials/update")
async def update_credentials(token: str = Form(...), _auth: bool = Depends(require_session)):
    raw = (token or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="API token is required")
    if not await validate_api_token(raw):
        raise HTTPException(status_code=400, detail="Invalid Hitem3D API credentials")
    save_hitem3d_credentials(raw)
    return {"saved": True}


@app.get("/download")
async def download(path: str, request: Request, _auth: bool = Depends(require_session)):
    """Serve a generated file from output/ by filename only (no path traversal)."""
    if not path or ".." in path or "/" in path or "\\" in path:
        raise HTTPException(status_code=400, detail="Invalid path")
    full = (OUTPUT_DIR / path).resolve()
    if not full.is_file() or OUTPUT_DIR not in full.parents:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full, filename=full.name)

@app.get("/models")
async def get_models(request: Request, _auth: bool = Depends(require_session)):
    """Get available processing models and options."""
    return get_available_models()

@app.post("/validate-token")
async def validate_token(token: str):
    """Validate Hitem3D API token."""
    is_valid = await validate_api_token(token)
    return {"valid": is_valid}

@app.get("/credentials/availability")
async def credentials_availability(request: Request, _auth: bool = Depends(require_session)):
    """Check if server-side Hitem3D credentials are available."""
    creds = resolve_hitem3d_credentials(None)
    available = bool(creds["access_token"] or (creds["client_id"] and creds["client_secret"]))
    return {"available": available}
