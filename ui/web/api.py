from fastapi import FastAPI, UploadFile, Request, Form, HTTPException, Depends
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    FileResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
import shutil
import os
import re
import platform
import psutil
import asyncio
import time
import uuid
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
from core.unified_pipeline import (
    run_pipeline_async,
    get_available_models,
    validate_api_token,
    resolve_hitem3d_credentials,
    save_hitem3d_credentials,
    get_hitem3d_balance,
)
from core.hitem3d_api import InsufficientBalanceError
from core.auth import (
    is_password_configured,
    verify_password,
    verify_session_token,
    create_session_token,
    set_password,
)
from core.user_db import (
    create_user,
    verify_user,
    get_user,
    get_user_by_username,
    admin_exists,
    get_all_users,
    delete_user,
    update_user_password,
    reset_user_trial,
    is_user_admin,
    get_user_trial,
    has_trial_available as db_has_trial_available,
    use_user_trial as db_use_user_trial,
    has_valid_license as db_has_valid_license,
    get_user_license as db_get_user_license,
    add_user_license as db_add_user_license,
    get_user_credits as db_get_user_credits,
    deduct_user_credits as db_deduct_user_credits,
)
from config.settings import get_output_dir

app = FastAPI()

OUTPUT_DIR = get_output_dir()
SESSION_COOKIE = "imagetoad_session"

# Mount static files directory for serving output files
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
SESSION_MAX_AGE = 24 * 3600
JOBS: Dict[str, Dict[str, Any]] = {}
JOB_RETENTION_SECONDS = 6 * 3600


def _prune_jobs():
    now = time.time()
    expired = [
        key
        for key, job in JOBS.items()
        if now - job.get("updated_at", now) > JOB_RETENTION_SECONDS
    ]
    for key in expired:
        JOBS.pop(key, None)
    if len(JOBS) > 200:
        ordered = sorted(JOBS.items(), key=lambda item: item[1].get("updated_at", 0))
        for key, _ in ordered[: len(JOBS) - 200]:
            JOBS.pop(key, None)


def _get_session(request: Request) -> Optional[str]:
    return request.cookies.get(SESSION_COOKIE)


async def require_session(request: Request) -> bool:
    """Dependency: require valid session when password is configured. Raises 401 otherwise."""
    if not is_password_configured():
        raise HTTPException(status_code=401, detail="Authentication required")
    token = _get_session(request)
    if verify_session_token(token or ""):
        return True
    raise HTTPException(status_code=401, detail="Authentication required")


def _main_app_html():
    """Return the main app HTML matching desktop app layout."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Image → 3D Pro</title>
        <style>
            * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }

            body {
                font-family: "Segoe UI", "Inter", system-ui, sans-serif;
                background-color: #111111;
                color: #e5e7eb;
                min-height: 100vh;
                display: flex;
            }

            /* ── Sidebar ── */
            .sidebar {
                width: 260px;
                background-color: #0a0a0a;
                border-right: 1px solid #1e293b;
                display: flex;
                flex-direction: column;
                padding: 20px 16px;
                flex-shrink: 0;
            }

            .logo-container {
                text-align: center;
                margin-bottom: 24px;
            }

            .logo {
                font-size: 20px;
                font-weight: 700;
                color: #60a5fa;
                margin-bottom: 4px;
            }

            .version {
                color: #64748b;
                font-size: 11px;
                font-weight: 500;
            }

            /* ── Group Boxes ── */
            .group-box {
                border: 1px solid #1e293b;
                border-radius: 8px;
                margin-top: 12px;
                padding: 16px 12px 12px 12px;
                background-color: #161616;
                position: relative;
            }

            .group-box-title {
                position: absolute;
                top: -10px;
                left: 12px;
                background-color: #161616;
                padding: 0 6px;
                color: #60a5fa;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
            }

            .group-box#deviceBox {
                border-color: #3b82f6;
            }

            .form-row {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 6px;
                font-size: 12px;
            }

            .form-row:last-child {
                margin-bottom: 0;
            }

            .form-label {
                color: #94a3b8;
            }

            .form-value {
                color: #e5e7eb;
                font-family: 'JetBrains Mono', monospace;
            }

            .form-value.highlight {
                color: #60a5fa;
                font-weight: 600;
            }

            .form-value.success {
                color: #22c55e;
                font-weight: 600;
            }

            /* ── Main Content ── */
            .main-content {
                flex: 1;
                display: flex;
                flex-direction: column;
                padding: 20px 24px;
                overflow-y: auto;
            }

            .content-row {
                display: flex;
                gap: 16px;
                margin-bottom: 16px;
            }

            .content-row > * {
                flex: 1;
            }

            /* ── Inputs ── */
            input[type="text"], select {
                width: 100%;
                padding: 8px 12px;
                border: 1px solid #334155;
                border-radius: 6px;
                background-color: #0f172a;
                color: #e5e7eb;
                font-size: 13px;
                font-family: inherit;
            }

            input[type="text"]:focus, select:focus {
                outline: none;
                border-color: #60a5fa;
            }

            input[type="file"] {
                display: none;
            }

            /* ── Buttons ── */
            button {
                padding: 8px 16px;
                border-radius: 6px;
                border: 1px solid #334155;
                background-color: #1e293b;
                color: #e5e7eb;
                font-weight: 600;
                font-size: 13px;
                cursor: pointer;
                transition: all 0.15s ease;
            }

            button:hover {
                background-color: #334155;
                border-color: #60a5fa;
            }

            button:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }

            button.primary {
                background: linear-gradient(135deg, #22c55e, #16a34a);
                border: none;
                color: white;
            }

            button.primary:hover {
                filter: brightness(1.1);
            }

            button.secondary {
                background-color: #1e293b;
            }

            button.danger {
                background-color: #ef4444;
                border-color: #ef4444;
                color: white;
            }

            button.danger:hover {
                background-color: #dc2626;
            }

            /* ── File Input ── */
            .file-input-row {
                display: flex;
                gap: 8px;
            }

            .file-input-row input[type="text"] {
                flex: 1;
            }

            /* ── Dropzone ── */
            .dropzone {
                border: 2px dashed #334155;
                border-radius: 8px;
                padding: 40px 20px;
                text-align: center;
                cursor: pointer;
                background-color: #0f172a;
                transition: all 0.15s ease;
                color: #64748b;
                font-size: 13px;
            }

            .dropzone:hover {
                border-color: #60a5fa;
                color: #94a3b8;
            }

            .dropzone.dragover {
                border-color: #22c55e;
                background-color: rgba(34, 197, 94, 0.1);
            }

            /* ── Preview ── */
            .preview-container {
                min-height: 180px;
                border: 2px dashed #334155;
                border-radius: 8px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #64748b;
                font-size: 12px;
                overflow: hidden;
            }

            .preview-container img {
                max-width: 100%;
                max-height: 200px;
                object-fit: contain;
            }

            /* ── Progress Section ── */
            .progress-bar-container {
                margin-bottom: 10px;
            }

            .progress-bar {
                width: 100%;
                height: 28px;
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                overflow: hidden;
                position: relative;
            }

            .progress-fill {
                height: 100%;
                background: linear-gradient(90deg, #06b6d4, #3b82f6, #8b5cf6, #ec4899, #f59e0b, #10b981);
                background-size: 200% 100%;
                border-radius: 8px;
                transition: width 0.3s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
                font-size: 13px;
            }

            .task-container {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 10px;
            }

            .task-icon {
                font-size: 20px;
                width: 28px;
                text-align: center;
            }

            .task-message {
                flex: 1;
                background-color: #1e293b;
                border-radius: 6px;
                padding: 8px 12px;
                color: #e5e7eb;
                font-size: 13px;
                font-weight: 500;
            }

            .time-row {
                display: flex;
                justify-content: space-between;
                font-size: 11px;
                color: #64748b;
                font-family: 'JetBrains Mono', monospace;
            }

            .status-text {
                color: #60a5fa;
                font-size: 12px;
                font-weight: 600;
                margin-top: 8px;
            }

            /* ── Output Section ── */
            .output-grid {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 12px;
            }

            .output-card {
                background-color: #0f172a;
                border-radius: 6px;
                padding: 10px;
            }

            .output-header {
                color: #60a5fa;
                font-size: 12px;
                font-weight: 700;
                margin-bottom: 6px;
            }

            .output-path {
                color: #64748b;
                font-size: 10px;
                font-family: 'JetBrains Mono', monospace;
                margin-bottom: 8px;
                word-break: break-all;
            }

            .output-buttons {
                display: flex;
                gap: 6px;
            }

            .output-buttons button {
                flex: 1;
                padding: 4px 8px;
                font-size: 10px;
            }

            /* ── Activity Log ── */
            .activity-log-container {
                max-height: 180px;
                overflow-y: auto;
                background-color: #0f172a;
                border-radius: 4px;
                padding: 8px;
            }

            .activity-log-container::-webkit-scrollbar {
                width: 6px;
            }

            .activity-log-container::-webkit-scrollbar-track {
                background: transparent;
            }

            .activity-log-container::-webkit-scrollbar-thumb {
                background: rgba(55, 65, 81, 0.6);
                border-radius: 3px;
            }

            .log-entry {
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 6px 0;
                border-bottom: 1px solid rgba(55, 65, 81, 0.3);
                animation: fadeInSlide 0.3s ease-out;
            }

            .log-entry:last-child {
                border-bottom: none;
            }

            .log-icon {
                font-size: 14px;
                width: 24px;
                text-align: center;
            }

            .log-timestamp {
                color: #64748b;
                font-size: 10px;
                font-family: 'JetBrains Mono', monospace;
                min-width: 40px;
            }

            .log-message {
                color: #e5e7eb;
                font-size: 11px;
                flex: 1;
            }

            @keyframes fadeInSlide {
                from { opacity: 0; transform: translateX(-10px); }
                to { opacity: 1; transform: translateX(0); }
            }

            /* ── Action Buttons ── */
            .action-buttons {
                display: flex;
                justify-content: center;
                gap: 12px;
                margin-top: auto;
                padding-top: 16px;
            }

            .action-buttons button {
                min-width: 120px;
            }

            .action-buttons button.primary {
                min-width: 180px;
                min-height: 40px;
                font-size: 14px;
            }

            /* ── Radio Buttons ── */
            .radio-group {
                display: flex;
                gap: 16px;
            }

            .radio-option {
                display: flex;
                align-items: center;
                gap: 6px;
            }

            input[type="radio"] {
                accent-color: #3b82f6;
            }

            /* ── API Options ── */
            .api-options {
                display: none;
                margin-top: 12px;
                padding-top: 12px;
                border-top: 1px solid #334155;
            }

            .api-options.active {
                display: block;
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

            .model-info {
                margin-top: 8px;
                padding: 8px 12px;
                background: rgba(59, 130, 246, 0.1);
                border-left: 3px solid #3b82f6;
                border-radius: 4px;
                font-size: 12px;
                color: #93c5fd;
            }

            .balance-box {
                margin-top: 8px;
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 12px;
                border-left: 3px solid rgba(148, 163, 184, 0.6);
                background: rgba(30, 41, 59, 0.6);
                color: #cbd5f5;
            }

            .balance-ok {
                border-left-color: #22c55e;
                background: rgba(21, 128, 61, 0.15);
                color: #a7f3d0;
            }

            .balance-warn {
                border-left-color: #f59e0b;
                background: rgba(251, 191, 36, 0.12);
                color: #fcd34d;
            }

            .balance-error {
                border-left-color: #ef4444;
                background: rgba(127, 29, 29, 0.2);
                color: #fecdd3;
            }

            /* ── Warning & Error Boxes ── */
            .warning-box {
                background: linear-gradient(135deg, rgba(251, 191, 36, 0.15), rgba(245, 158, 11, 0.1));
                border: 1px solid rgba(251, 191, 36, 0.45);
                border-left: 4px solid #f59e0b;
                border-radius: 8px;
                padding: 12px 14px;
                margin: 10px 0;
                color: #fbbf24;
                font-size: 12px;
            }

            .error-box {
                background: linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(220, 38, 38, 0.1));
                border: 1px solid rgba(239, 68, 68, 0.45);
                border-left: 4px solid #ef4444;
                border-radius: 8px;
                padding: 12px 14px;
                margin: 10px 0;
                color: #fca5a5;
                font-size: 12px;
            }

            .download-links {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 10px;
            }

            .download-links a {
                display: inline-block;
                padding: 6px 12px;
                border-radius: 8px;
                background: rgba(34, 197, 94, 0.2);
                color: #22c55e;
                text-decoration: none;
                font-size: 13px;
            }

            .download-links a:hover {
                background: rgba(34, 197, 94, 0.35);
            }
        </style>
    </head>
    <body>
        <!-- Sidebar -->
        <aside class="sidebar">
            <div class="logo-container">
                <div class="logo">🎨 Image → 3D Pro</div>
                <div class="version">v2.0.0</div>
            </div>

            <!-- Device Info -->
            <div class="group-box" id="deviceBox">
                <div class="group-box-title">🔒 Device</div>
                <div class="form-row">
                    <span class="form-label">ID:</span>
                    <span class="form-value highlight" id="deviceId">--</span>
                </div>
                <div class="form-row">
                    <span class="form-label">Host:</span>
                    <span class="form-value" id="deviceHost">--</span>
                </div>
                <div class="form-row">
                    <span class="form-label">Status:</span>
                    <span class="form-value success">✓ Secured</span>
                </div>
            </div>

            <!-- System Panel -->
            <div class="group-box">
                <div class="group-box-title">⚙️ System</div>
                <div class="form-row">
                    <span class="form-label">RAM:</span>
                    <span class="form-value" id="sysRam">-- / --</span>
                </div>
                <div class="form-row">
                    <span class="form-label">CPU:</span>
                    <span class="form-value" id="sysCpu">--</span>
                </div>
                <div class="form-row">
                    <span class="form-label">Platform:</span>
                    <span class="form-value" id="sysPlatform" style="font-size: 10px;">--</span>
                </div>
                <div class="form-row">
                    <span class="form-label">Mode:</span>
                    <span class="form-value success" id="sysMode">Local</span>
                </div>
            </div>

            <div style="margin-top: auto;">
                <button class="secondary" onclick="logout()" style="width: 100%; margin-bottom: 8px;">🔒 Log Out</button>
                <button class="danger" onclick="quitApp()" style="width: 100%;">✕ Quit</button>
            </div>
        </aside>

        <!-- Main Content -->
        <main class="main-content">
            <!-- Row 1: Source + Processing Options -->
            <div class="content-row">
                <!-- Source Section -->
                <div class="group-box" style="flex: 1;">
                    <div class="group-box-title">📷 Source</div>
                    <div class="file-input-row">
                        <input type="text" id="filePath" placeholder="Select image file..." readonly />
                        <button onclick="document.getElementById('fileInput').click()">Browse…</button>
                    </div>
                    <input type="file" id="fileInput" accept="image/*" />
                </div>

                <!-- Processing Options -->
                <div class="group-box" style="flex: 2;">
                    <div class="group-box-title">⚙️ Processing</div>
                    
                    <div class="option-group">
                        <label class="option-label">Method</label>
                        <div class="radio-group">
                            <div class="radio-option">
                                <input type="radio" id="local" name="processing" value="local" checked>
                                <label for="local">Local Processing</label>
                            </div>
                            <div class="radio-option">
                                <input type="radio" id="api" name="processing" value="api">
                                <label for="api">Cloud API</label>
                            </div>
                        </div>
                    </div>

                    <div id="localOptions">
                        <div class="option-group">
                            <label class="option-label" for="quality">Quality</label>
                            <select id="quality">
                                <option value="draft">Draft</option>
                                <option value="standard" selected>Standard</option>
                                <option value="high">High</option>
                                <option value="production">Production</option>
                            </select>
                        </div>
                    </div>

                    <div class="api-options" id="apiOptions">
                        <div class="option-group">
                            <label class="option-label" for="apiToken">API Token</label>
                            <input type="text" id="apiToken" placeholder="Enter your Cloud API token">
                        </div>

                        <div class="option-group">
                            <label class="option-label" for="apiModel">Model</label>
                            <select id="apiModel">
                                <option value="hitem3dv1.5">Standard v1.5</option>
                                <option value="hitem3dv2.0">Standard v2.0</option>
                                <option value="scene-portraitv1.5">Portrait v1.5</option>
                                <option value="scene-portraitv2.0">Portrait v2.0</option>
                                <option value="scene-portraitv2.1">Portrait v2.1</option>
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

                        <div class="option-group">
                            <label class="option-label">Balance</label>
                            <div class="balance-box" id="balanceInfo">Enter token to check balance</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Row 2: Preview + Progress -->
            <div class="content-row">
                <!-- Preview Section -->
                <div class="group-box" style="flex: 1;">
                    <div class="group-box-title">🖼️ Preview</div>
                    <div class="preview-container" id="previewContainer">
                        <span>No image selected</span>
                    </div>
                </div>

                <!-- Progress Section -->
                <div class="group-box" style="flex: 1;">
                    <div class="group-box-title">📊 Progress</div>
                    
                    <div class="progress-bar-container">
                        <div class="progress-bar">
                            <div class="progress-fill" id="progressFill" style="width: 0%;">0%</div>
                        </div>
                    </div>

                    <div class="task-container">
                        <div class="task-icon" id="taskIcon">⏳</div>
                        <div class="task-message" id="taskMessage">Ready</div>
                    </div>

                    <div class="time-row">
                        <span id="elapsedTime">Elapsed: --:--</span>
                        <span id="etaTime">ETA: --:--</span>
                    </div>

                    <div class="status-text" id="statusText"></div>
                </div>
            </div>

            <!-- Row 3: Outputs -->
            <div class="group-box">
                <div class="group-box-title">📦 Outputs</div>
                <div class="output-grid">
                    <div class="output-card">
                        <div class="output-header">OBJ</div>
                        <div class="output-path" id="objPath">—</div>
                        <div class="output-buttons">
                            <button onclick="openOutput('obj')">Open</button>
                            <button onclick="saveOutput('obj')">Save</button>
                        </div>
                    </div>
                    <div class="output-card">
                        <div class="output-header">STL</div>
                        <div class="output-path" id="stlPath">—</div>
                        <div class="output-buttons">
                            <button onclick="openOutput('stl')">Open</button>
                            <button onclick="saveOutput('stl')">Save</button>
                        </div>
                    </div>
                    <div class="output-card">
                        <div class="output-header">GLB</div>
                        <div class="output-path" id="glbPath">—</div>
                        <div class="output-buttons">
                            <button onclick="openOutput('glb')">Open</button>
                            <button onclick="saveOutput('glb')">Save</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Row 4: Activity Log -->
            <div class="group-box">
                <div class="group-box-title">📋 Activity Log</div>
                <div class="activity-log-container" id="activityLog">
                    <!-- Log entries will be added here -->
                </div>
            </div>

            <!-- Row 5: Action Buttons -->
            <div class="action-buttons">
                <button class="secondary" onclick="resetUI()">🔄 Reset</button>
                <button class="secondary" onclick="openOutputFolder()">📂 Open Folder</button>
                <button class="primary" id="generateBtn" onclick="startGeneration()" disabled>🚀 Generate 3D Model</button>
            </div>

            <!-- Results Container -->
            <div id="resultsContainer"></div>
        </main>

        <script>
            // State
            let selectedFile = null;
            let jobId = null;
            let progressTimer = null;
            let startTime = null;
            let logEntries = [];
            let logStartTime = null;
            let outputs = {};

            // Model info
            const modelInfo = {
                'hitem3dv1.5': {
                    desc: 'General purpose 3D generation model. Recommended resolution: 1024',
                    resolutions: ['512', '1024', '1536', '1536pro']
                },
                'hitem3dv2.0': {
                    desc: 'Enhanced 3D generation model with better quality. Recommended resolution: 1536',
                    resolutions: ['1536', '1536pro']
                },
                'scene-portraitv1.5': {
                    desc: 'Specialized portrait model. Recommended resolution: 1536',
                    resolutions: ['1536']
                },
                'scene-portraitv2.0': {
                    desc: 'Specialized portrait model. Recommended resolution: 1536pro',
                    resolutions: ['1536pro']
                },
                'scene-portraitv2.1': {
                    desc: 'Specialized portrait model. Recommended resolution: 1536pro',
                    resolutions: ['1536pro']
                }
            };

            // Log icons mapping
            const logIcons = {
                'starting': '🚀', 'start': '🚀', 'init': '⚙️',
                'loading': '📥', 'load': '📥', 'preprocess': '🔧',
                'processing': '⚡', 'model': '🤖', 'inference': '🤖',
                'generate': '✨', 'generation': '✨', 'mesh': '📐',
                'geometry': '📐', 'texture': '🎨', 'texturing': '🎨',
                'material': '🎨', 'export': '💾', 'save': '💾',
                'upload': '☁️', 'api': '☁️', 'complete': '✅',
                'done': '✅', 'finish': '✅', 'success': '✅',
                'error': '❌', 'fail': '❌', 'warning': '⚠️',
                'warn': '⚠️', 'info': 'ℹ️', 'file': '📄', 'files': '📦'
            };

            // Task icons
            const taskIcons = {
                'preprocess': '🔧', 'preprocessing': '🔧', 'loading': '📥',
                'load': '📥', 'model': '🤖', 'inference': '🤖', 'predict': '🤖',
                'generation': '✨', 'generate': '✨', 'mesh': '📐',
                'geometry': '📐', 'texture': '🎨', 'texturing': '🎨',
                'material': '🎨', 'export': '💾', 'save': '💾',
                'upload': '☁️', 'api': '☁️', 'complete': '✅',
                'done': '✅', 'finish': '✅'
            };

            // Initialize
            document.addEventListener('DOMContentLoaded', () => {
                updateSystemInfo();
                setInterval(updateSystemInfo, 5000);
                
                // File input handler
                document.getElementById('fileInput').addEventListener('change', handleFileSelect);
                
                // Processing method toggle
                document.querySelectorAll('input[name="processing"]').forEach(radio => {
                    radio.addEventListener('change', toggleProcessingMethod);
                });
                
                // Model change handler
                document.getElementById('apiModel').addEventListener('change', updateModelInfo);
                
                // API token change handler
                document.getElementById('apiToken').addEventListener('input', scheduleBalanceCheck);
                
                // Update resolution options based on model
                updateResolutionOptions();
            });

            function updateSystemInfo() {
                fetch('/system-info')
                    .then(r => r.json())
                    .then(data => {
                        document.getElementById('deviceId').textContent = data.device_id || '--';
                        document.getElementById('deviceHost').textContent = data.hostname || '--';
                        document.getElementById('sysRam').textContent = 
                            `${data.ram_available_gb?.toFixed(2) || '--'} / ${data.ram_total_gb?.toFixed(2) || '--'} GB`;
                        document.getElementById('sysCpu').textContent = data.cpu_count || '--';
                        document.getElementById('sysPlatform').textContent = 
                            `${data.platform || '--'} ${data.release || ''}`;
                    })
                    .catch(() => {});
            }

            function handleFileSelect(e) {
                const file = e.target.files[0];
                if (!file) return;
                
                selectedFile = file;
                document.getElementById('filePath').value = file.name;
                
                // Show preview
                const reader = new FileReader();
                reader.onload = (e) => {
                    const container = document.getElementById('previewContainer');
                    container.innerHTML = `<img src="${e.target.result}" alt="Preview" />`;
                };
                reader.readAsDataURL(file);
                
                document.getElementById('generateBtn').disabled = false;
                addLogEntry(`📷 Selected: ${file.name}`);
            }

            function toggleProcessingMethod() {
                const useApi = document.getElementById('api').checked;
                document.getElementById('localOptions').style.display = useApi ? 'none' : 'block';
                document.getElementById('apiOptions').classList.toggle('active', useApi);
                document.getElementById('sysMode').textContent = useApi ? 'Cloud API' : 'Local';
                document.getElementById('sysMode').className = useApi ? 
                    'form-value highlight' : 'form-value success';
                
                if (useApi) {
                    scheduleBalanceCheck();
                }
            }

            function updateModelInfo() {
                const model = document.getElementById('apiModel').value;
                const info = modelInfo[model];
                if (info) {
                    document.getElementById('modelInfo').textContent = info.desc;
                    updateResolutionOptions();
                }
            }

            function updateResolutionOptions() {
                const model = document.getElementById('apiModel').value;
                const info = modelInfo[model];
                const select = document.getElementById('apiResolution');
                
                if (info && info.resolutions) {
                    select.innerHTML = info.resolutions.map(r => 
                        `<option value="${r}">${r === '1536pro' ? '1536³ Pro' : r + '³'}</option>`
                    ).join('');
                }
            }

            let balanceTimer = null;
            function scheduleBalanceCheck() {
                if (balanceTimer) clearTimeout(balanceTimer);
                balanceTimer = setTimeout(checkBalance, 600);
            }

            function checkBalance() {
                const useApi = document.getElementById('api').checked;
                if (!useApi) return;
                
                const token = document.getElementById('apiToken').value.trim();
                if (!token) {
                    document.getElementById('balanceInfo').textContent = 'Enter token to check balance';
                    document.getElementById('balanceInfo').className = 'balance-box';
                    return;
                }
                
                document.getElementById('balanceInfo').textContent = 'Checking balance...';
                
                fetch('/hitem3d/balance', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: `api_token=${encodeURIComponent(token)}`
                })
                .then(r => r.json())
                .then(data => {
                    if (data.available !== undefined) {
                        document.getElementById('balanceInfo').textContent = 
                            `Balance: ${data.available} credits`;
                        document.getElementById('balanceInfo').className = 'balance-box balance-ok';
                    } else {
                        throw new Error('Balance unavailable');
                    }
                })
                .catch(err => {
                    document.getElementById('balanceInfo').textContent = 
                        'Balance check failed: ' + err.message;
                    document.getElementById('balanceInfo').className = 'balance-box balance-error';
                });
            }

            function addLogEntry(message) {
                if (!logStartTime) logStartTime = Date.now();
                
                const elapsed = Math.floor((Date.now() - logStartTime) / 1000);
                const mins = Math.floor(elapsed / 60);
                const secs = elapsed % 60;
                const timeStr = `${mins}:${secs.toString().padStart(2, '0')}`;
                
                // Find icon
                let icon = '📋';
                const msgLower = message.toLowerCase();
                for (const [key, value] of Object.entries(logIcons)) {
                    if (msgLower.includes(key)) {
                        icon = value;
                        break;
                    }
                }
                
                const entry = document.createElement('div');
                entry.className = 'log-entry';
                entry.innerHTML = `
                    <span class="log-icon">${icon}</span>
                    <span class="log-timestamp">${timeStr}</span>
                    <span class="log-message">${message}</span>
                `;
                
                const log = document.getElementById('activityLog');
                log.appendChild(entry);
                log.scrollTop = log.scrollHeight;
            }

            function updateTaskIcon(message) {
                let icon = '⏳';
                const msgLower = message.toLowerCase();
                for (const [key, value] of Object.entries(taskIcons)) {
                    if (msgLower.includes(key)) {
                        icon = value;
                        break;
                    }
                }
                document.getElementById('taskIcon').textContent = icon;
            }

            function updateProgress(percent, message) {
                const fill = document.getElementById('progressFill');
                fill.style.width = percent + '%';
                fill.textContent = Math.round(percent) + '%';
                
                if (message) {
                    document.getElementById('taskMessage').textContent = message;
                    updateTaskIcon(message);
                }
                
                if (startTime && percent > 0 && percent < 100) {
                    const elapsed = (Date.now() - startTime) / 1000;
                    const eta = (elapsed / percent) * (100 - percent);
                    document.getElementById('elapsedTime').textContent = 
                        'Elapsed: ' + formatTime(elapsed);
                    document.getElementById('etaTime').textContent = 
                        'ETA: ' + formatTime(eta);
                }
            }

            function formatTime(seconds) {
                const mins = Math.floor(seconds / 60);
                const secs = Math.floor(seconds % 60);
                return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
            }

            async function startGeneration() {
                if (!selectedFile) return;
                
                const useApi = document.getElementById('api').checked;
                const formData = new FormData();
                formData.append('image', selectedFile);
                formData.append('processing', useApi ? 'api' : 'local');
                
                if (useApi) {
                    formData.append('api_token', document.getElementById('apiToken').value);
                    formData.append('api_model', document.getElementById('apiModel').value);
                    formData.append('api_resolution', document.getElementById('apiResolution').value);
                    formData.append('api_format', document.getElementById('apiFormat').value);
                } else {
                    formData.append('quality', document.getElementById('quality').value);
                }
                
                document.getElementById('generateBtn').disabled = true;
                startTime = Date.now();
                logStartTime = Date.now();
                logEntries = [];
                document.getElementById('activityLog').innerHTML = '';
                
                const methodText = useApi ? 'Cloud API' : 'Local Processing';
                addLogEntry(`🚀 Starting pipeline with ${methodText}`);
                if (useApi) {
                    addLogEntry(`   Model: ${document.getElementById('apiModel').value}, Res: ${document.getElementById('apiResolution').value}`);
                }
                
                updateProgress(0, `Starting ${methodText}...`);
                
                try {
                    const response = await fetch('/generate', {
                        method: 'POST',
                        body: formData
                    });
                    
                    if (!response.ok) {
                        throw new Error('Upload failed');
                    }
                    
                    const data = await response.json();
                    jobId = data.job_id;
                    
                    // Start polling
                    pollJob();
                } catch (err) {
                    addLogEntry(`❌ Error: ${err.message}`);
                    document.getElementById('statusText').textContent = '❌ Failed';
                    document.getElementById('statusText').style.color = '#ef4444';
                    document.getElementById('generateBtn').disabled = false;
                }
            }

            async function pollJob() {
                while (jobId) {
                    await new Promise(r => setTimeout(r, 2000));
                    
                    try {
                        const response = await fetch(`/job/${jobId}`);
                        const data = await response.json();
                        
                        if (data.progress_percent !== undefined) {
                            updateProgress(data.progress_percent, data.current_stage_msg || 'Processing...');
                        }
                        
                        if (data.progress_log) {
                            data.progress_log.forEach(entry => {
                                addLogEntry(entry.msg);
                            });
                        }
                        
                        if (data.status === 'done') {
                            handleComplete(data.result);
                            break;
                        } else if (data.status === 'error') {
                            throw new Error(data.error || 'Processing failed');
                        }
                    } catch (err) {
                        addLogEntry(`❌ Error: ${err.message}`);
                        document.getElementById('statusText').textContent = '❌ Failed';
                        document.getElementById('statusText').style.color = '#ef4444';
                        break;
                    }
                }
                
                document.getElementById('generateBtn').disabled = false;
            }

            function handleComplete(result) {
                updateProgress(100, 'Complete! Your 3D model is ready.');
                document.getElementById('taskIcon').textContent = '✅';
                document.getElementById('statusText').textContent = '✅ Completed';
                document.getElementById('statusText').style.color = '#22c55e';
                document.getElementById('etaTime').textContent = 'ETA: 00:00';
                
                outputs = result;
                
                // Update output paths
                if (result.obj) {
                    document.getElementById('objPath').textContent = result.obj.split('/').pop();
                    document.getElementById('objPath').style.color = '#22c55e';
                }
                if (result.stl) {
                    document.getElementById('stlPath').textContent = result.stl.split('/').pop();
                    document.getElementById('stlPath').style.color = '#22c55e';
                }
                if (result.glb) {
                    document.getElementById('glbPath').textContent = result.glb.split('/').pop();
                    document.getElementById('glbPath').style.color = '#22c55e';
                }
                
                // Show results
                let html = '<div class="download-links">';
                if (result.obj) html += `<a href="${result.obj}" download>Download OBJ</a>`;
                if (result.stl) html += `<a href="${result.stl}" download>Download STL</a>`;
                if (result.glb) html += `<a href="${result.glb}" download>Download GLB</a>`;
                if (result.fbx) html += `<a href="${result.fbx}" download>Download FBX</a>`;
                if (result.usdz) html += `<a href="${result.usdz}" download>Download USDZ</a>`;
                html += '</div>';
                
                document.getElementById('resultsContainer').innerHTML = html;
                
                addLogEntry('✅ Processing completed successfully');
                if (result.stats && result.stats.total_seconds) {
                    addLogEntry(`✅ Done! Total time: ${result.stats.total_seconds.toFixed(1)}s`);
                }
            }

            function resetUI() {
                selectedFile = null;
                outputs = {};
                document.getElementById('fileInput').value = '';
                document.getElementById('filePath').value = '';
                document.getElementById('previewContainer').innerHTML = '<span>No image selected</span>';
                document.getElementById('progressFill').style.width = '0%';
                document.getElementById('progressFill').textContent = '0%';
                document.getElementById('taskIcon').textContent = '⏳';
                document.getElementById('taskMessage').textContent = 'Ready';
                document.getElementById('elapsedTime').textContent = 'Elapsed: --:--';
                document.getElementById('etaTime').textContent = 'ETA: --:--';
                document.getElementById('statusText').textContent = '';
                document.getElementById('activityLog').innerHTML = '';
                document.getElementById('resultsContainer').innerHTML = '';
                document.getElementById('generateBtn').disabled = true;
                
                ['obj', 'stl', 'glb'].forEach(fmt => {
                    document.getElementById(fmt + 'Path').textContent = '—';
                    document.getElementById(fmt + 'Path').style.color = '#64748b';
                });
                
                logStartTime = null;
                logEntries = [];
                addLogEntry('🔄 Reset');
            }

            function openOutput(format) {
                const path = outputs[format];
                if (path) {
                    window.open(path, '_blank');
                }
            }

            function saveOutput(format) {
                const path = outputs[format];
                if (path) {
                    const link = document.createElement('a');
                    link.href = path;
                    link.download = path.split('/').pop();
                    link.click();
                }
            }

            function openOutputFolder() {
                window.open('/output', '_blank');
            }

            function logout() {
                window.location.href = '/logout';
            }

            function quitApp() {
                if (confirm('Are you sure you want to quit?')) {
                    window.close();
                }
            }

            // Drag and drop
            const dropzone = document.body;
            
            dropzone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropzone.classList.add('dragover');
            });
            
            dropzone.addEventListener('dragleave', () => {
                dropzone.classList.remove('dragover');
            });
            
            dropzone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropzone.classList.remove('dragover');
                
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    document.getElementById('fileInput').files = files;
                    handleFileSelect({ target: { files: files } });
                }
            });
        </script>
    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main application page or login if not authenticated."""
    token = _get_session(request)
    if is_password_configured() and not verify_session_token(token or ""):
        return RedirectResponse(url="/login", status_code=302)
    return HTMLResponse(content=_main_app_html())


@app.get("/system-info")
async def get_system_info():
    """Get current system information."""
    try:
        mem = psutil.virtual_memory()
        import socket

        return {
            "device_id": str(uuid.uuid4())[:8].upper(),
            "hostname": socket.gethostname()[:20],
            "ram_available_gb": mem.available / (1024**3),
            "ram_total_gb": mem.total / (1024**3),
            "cpu_count": os.cpu_count(),
            "platform": platform.system(),
            "release": platform.release(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate")
async def generate(
    request: Request,
    image: UploadFile,
    processing: str = Form("local"),
    api_token: Optional[str] = Form(None),
    api_model: Optional[str] = Form("hitem3dv1.5"),
    api_resolution: Optional[str] = Form("1024"),
    api_format: Optional[str] = Form("obj"),
    quality: Optional[str] = Form("standard"),
):
    """Start a new generation job."""
    _prune_jobs()

    job_id = str(uuid.uuid4())
    temp_path = Path(tempfile.gettempdir()) / f"{job_id}_{image.filename}"

    with open(temp_path, "wb") as f:
        shutil.copyfileobj(image.file, f)

    JOBS[job_id] = {
        "id": job_id,
        "status": "queued",
        "input_path": str(temp_path),
        "use_api": processing == "api",
        "api_token": api_token,
        "api_model": api_model,
        "api_resolution": api_resolution,
        "api_format": api_format,
        "quality": quality,
        "created_at": time.time(),
        "updated_at": time.time(),
        "progress_percent": 0,
        "current_stage_msg": "Initializing...",
        "progress_log": [],
        "result": None,
    }

    # Start processing in background
    asyncio.create_task(_process_job(job_id))

    return {"job_id": job_id}


async def _process_job(job_id: str):
    """Process a job asynchronously."""
    job = JOBS[job_id]
    job["status"] = "running"

    def progress_callback(stage, pct, msg):
        job["progress_percent"] = pct
        job["current_stage_msg"] = msg
        job["progress_log"].append({"stage": stage, "msg": msg, "ts": time.time()})
        job["updated_at"] = time.time()

    try:
        result = await run_pipeline_async(
            job["input_path"],
            use_api=job["use_api"],
            api_token=job["api_token"],
            api_model=job["api_model"],
            api_resolution=job["api_resolution"],
            api_format=job["api_format"],
            quality=job["quality"],
            progress_callback=progress_callback,
        )

        if result.get("error"):
            job["result"] = result
            job["status"] = "error"
            # Add error to log if not already there
            err_msg = result["error"]
            if not job["progress_log"] or job["progress_log"][-1]["msg"] != err_msg:
                job["progress_log"].append(
                    {"stage": "error", "msg": f"❌ Error: {err_msg}", "ts": time.time()}
                )
        else:
            job["result"] = result
            job["status"] = "done"

    except Exception as e:
        job["result"] = {"error": str(e)}
        job["status"] = "error"

    job["updated_at"] = time.time()


@app.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """Get the status of a job."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job_id,
        "status": job["status"],
        "progress_percent": job["progress_percent"],
        "current_stage_msg": job["current_stage_msg"],
        "current_stage": job["progress_log"][-1]["stage"]
        if job["progress_log"]
        else None,
        "progress_log": job["progress_log"],
        "result": job["result"],
        "error": job.get("result", {}).get("error") if job.get("result") else None,
    }


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Render the login page."""
    return HTMLResponse(
        content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - Image → 3D Pro</title>
        <style>
            body {
                font-family: "Segoe UI", system-ui, sans-serif;
                background-color: #111111;
                color: #e5e7eb;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
            }
            .login-card {
                background-color: #161616;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 32px;
                width: 100%;
                max-width: 400px;
            }
            h1 {
                color: #60a5fa;
                font-size: 24px;
                margin-bottom: 24px;
                text-align: center;
            }
            input {
                width: 100%;
                padding: 12px;
                margin-bottom: 16px;
                border: 1px solid #334155;
                border-radius: 6px;
                background-color: #0f172a;
                color: #e5e7eb;
                font-size: 14px;
            }
            button {
                width: 100%;
                padding: 12px;
                background: linear-gradient(135deg, #3b82f6, #2563eb);
                border: none;
                border-radius: 6px;
                color: white;
                font-weight: 600;
                font-size: 14px;
                cursor: pointer;
            }
            button:hover {
                filter: brightness(1.1);
            }
            .error {
                color: #ef4444;
                font-size: 13px;
                margin-bottom: 16px;
            }
        </style>
    </head>
    <body>
        <div class="login-card">
            <h1>🔒 Image → 3D Pro</h1>
            <form method="POST" action="/login">
                <input type="password" name="password" placeholder="Enter password" required />
                <button type="submit">Login</button>
            </form>
        </div>
    </body>
    </html>
    """
    )


@app.post("/login")
async def do_login(request: Request, password: str = Form(...)):
    """Handle login form submission."""
    if verify_password(password):
        token = create_session_token()
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
        return response
    return HTMLResponse(
        content="""
        <script>alert('Invalid password'); window.location.href='/login';</script>
        """,
        status_code=401,
    )


@app.get("/logout")
async def logout():
    """Logout and clear session."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.post("/hitem3d/balance")
async def check_balance(api_token: Optional[str] = Form(None)):
    """Check Hitem3D API balance."""
    try:
        credentials = resolve_hitem3d_credentials(api_token)
        result = await get_hitem3d_balance(api_token or None)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
