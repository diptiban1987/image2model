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
    load_saved_api_credentials,
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
    update_user_admin_status,
    update_user_credits,
    get_user_all_licenses,
    revoke_user_license,
    get_full_user_detail,
    update_user_details,
)
from config.settings import get_output_dir

app = FastAPI()

OUTPUT_DIR = get_output_dir()
SESSION_COOKIE = "imagetoad_session"
APP_WEB_VERSION = "2.1.0"
IS_RENDER = os.getenv("RENDER") is not None or os.getenv("PORT") is not None

# Mount static files directory for serving output files
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")


@app.get("/health")
async def health():
    return {"status": "ok", "version": APP_WEB_VERSION}


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
    """Dependency: require valid session when password is configured."""
    if not is_password_configured():
        return True
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

/* ── Compact API Section ── */
.api-row {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.api-row:last-child {
  margin-bottom: 0;
}

.api-field {
  flex: 1;
  min-width: 0;
}

.api-token-field {
  flex: 2;
}

.api-balance-field {
  flex: 1;
}

.api-input-group {
  display: flex;
  gap: 6px;
}

.api-input-group input[type="password"],
.api-input-group input[type="text"] {
  flex: 1;
  min-width: 0;
}

.icon-btn {
  padding: 8px 10px;
  min-width: 36px;
  font-size: 14px;
  background-color: #1e293b;
  border: 1px solid #334155;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.icon-btn:hover {
  background-color: #334155;
  border-color: #60a5fa;
}

.save-btn {
  background-color: rgba(34, 197, 94, 0.2);
  border-color: rgba(34, 197, 94, 0.5);
}

.save-btn:hover {
  background-color: rgba(34, 197, 94, 0.3);
  border-color: #22c55e;
}

.save-btn.saved {
  background-color: rgba(34, 197, 94, 0.4);
  border-color: #22c55e;
}

.api-config-row .api-field {
  flex: 1;
}

.api-status {
  font-size: 11px;
  margin-top: 4px;
  color: #22c55e;
  min-height: 16px;
}

.model-info.compact {
  margin-top: 8px;
  padding: 6px 10px;
  font-size: 11px;
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

            .source-tabs .tab-btn {
                background-color: #1e293b;
                border: 1px solid #334155;
            }

            .source-tabs .tab-btn.active {
                background-color: #3b82f6;
                border-color: #3b82f6;
                color: white;
            }
        </style>
    </head>
    <body>
        <!-- Sidebar -->
        <aside class="sidebar">
            <div class="logo-container">
                <div class="logo">🎨 Image → 3D Pro</div>
                <div class="version">v2.1.0</div>
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
                    <div class="source-tabs" style="display: flex; gap: 8px; margin-bottom: 12px;">
                        <button class="tab-btn active" id="imageTabBtn" onclick="switchSourceTab('image')" style="flex:1;">🖼️ Image</button>
                        <button class="tab-btn" id="textTabBtn" onclick="switchSourceTab('text')" style="flex:1;">✍️ Text</button>
                    </div>
                    <div id="imageSource">
                        <div class="file-input-row">
                            <input type="text" id="filePath" placeholder="Select image file..." readonly />
                            <button onclick="document.getElementById('fileInput').click()">Browse…</button>
                        </div>
                        <input type="file" id="fileInput" accept="image/*" />
                    </div>
                    <div id="textSource" style="display:none;">
                        <textarea id="textPrompt" rows="3" placeholder="Describe the 3D model...&#10;e.g., 'a red sports car' or 'a medieval castle'" style="width:100%; padding:8px; border:1px solid #334155; border-radius:6px; background-color:#0f172a; color:#e5e7eb; font-size:13px; resize:vertical;"></textarea>
                        <input type="text" id="negativePrompt" placeholder="Negative prompt (optional)" style="margin-top:8px;" />
                        <div class="warning-box" style="margin-top:8px;">⚠️ Text-to-3D requires a specific Cloud API key type (tsk_...)</div>
                    </div>
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
          <!-- Row 1: API Token with Save -->
          <div class="api-row">
            <div class="api-field api-token-field">
              <label class="option-label">API Token</label>
              <div class="api-input-group">
                <input type="password" id="apiToken" placeholder="Enter your Cloud API token">
                <button type="button" class="icon-btn" id="toggleTokenBtn" title="Show/Hide" onclick="toggleTokenVisibility()">👁</button>
                <button type="button" class="icon-btn save-btn" id="saveTokenBtn" title="Save credentials" onclick="saveApiCredentials()">💾</button>
              </div>
              <div class="api-status" id="apiTokenStatus"></div>
            </div>
            <div class="api-field api-balance-field">
              <label class="option-label">Balance</label>
              <div class="balance-box" id="balanceInfo">Enter token to check balance</div>
            </div>
          </div>

          <!-- Row 2: Model, Resolution, Format -->
          <div class="api-row api-config-row">
            <div class="api-field">
              <label class="option-label" for="apiModel">Model</label>
              <select id="apiModel">
                <option value="hitem3dv1.5">Standard v1.5</option>
                <option value="hitem3dv2.0">Standard v2.0</option>
                <option value="scene-portraitv1.5">Portrait v1.5</option>
                <option value="scene-portraitv2.0">Portrait v2.0</option>
                <option value="scene-portraitv2.1">Portrait v2.1</option>
              </select>
            </div>
            <div class="api-field">
              <label class="option-label" for="apiResolution">Resolution</label>
              <select id="apiResolution">
                <option value="512">512³</option>
                <option value="1024" selected>1024³</option>
                <option value="1536">1536³</option>
                <option value="1536pro">1536³ Pro</option>
              </select>
            </div>
            <div class="api-field">
              <label class="option-label" for="apiFormat">Format</label>
              <select id="apiFormat">
                <option value="obj" selected>OBJ</option>
                <option value="glb">GLB</option>
                <option value="stl">STL</option>
                <option value="fbx">FBX</option>
                <option value="usdz">USDZ</option>
              </select>
            </div>
          </div>
          <div class="model-info compact" id="modelInfo">
            Standard v1.5: General purpose 3D generation. Recommended: 1024³
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
            let lastLogIndex = 0;

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

  // Auto-fetch API credentials from Supabase or local storage
  fetchAutoCredentials();
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

function fetchAutoCredentials() {
  fetch('/auto-credentials')
    .then(r => r.json())
    .then(data => {
      if (data.success && data.token) {
        const tokenInput = document.getElementById('apiToken');
        if (tokenInput && !tokenInput.value) {
          tokenInput.value = data.token;
          // Trigger balance check after auto-loading
          if (document.getElementById('api').checked) {
            scheduleBalanceCheck();
          }
        }
      }
    })
    .catch(() => {
      // Silent fail - user can still enter token manually
    });
}

function toggleTokenVisibility() {
  const tokenInput = document.getElementById('apiToken');
  const toggleBtn = document.getElementById('toggleTokenBtn');
  if (tokenInput.type === 'password') {
    tokenInput.type = 'text';
    toggleBtn.textContent = '🙈';
    toggleBtn.title = 'Hide token';
  } else {
    tokenInput.type = 'password';
    toggleBtn.textContent = '👁';
    toggleBtn.title = 'Show token';
  }
}

function saveApiCredentials() {
  const tokenInput = document.getElementById('apiToken');
  const token = tokenInput.value.trim();
  const saveBtn = document.getElementById('saveTokenBtn');
  const statusEl = document.getElementById('apiTokenStatus');

  if (!token) {
    statusEl.textContent = '⚠️ Enter a token first';
    statusEl.style.color = '#f59e0b';
    setTimeout(() => { statusEl.textContent = ''; }, 3000);
    return;
  }

  // Send to backend to save
  fetch('/save-credentials', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `api_token=${encodeURIComponent(token)}`
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) {
      saveBtn.classList.add('saved');
      saveBtn.textContent = '✓';
      statusEl.textContent = '✓ Saved';
      statusEl.style.color = '#22c55e';
      addLogEntry('💾 API credentials saved');
      setTimeout(() => {
        saveBtn.textContent = '💾';
        statusEl.textContent = '';
      }, 2000);
    } else {
      throw new Error(data.error || 'Save failed');
    }
  })
  .catch(err => {
    statusEl.textContent = '❌ Save failed';
    statusEl.style.color = '#ef4444';
    setTimeout(() => { statusEl.textContent = ''; }, 3000);
  });
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

            function switchSourceTab(tab) {
                const isTextMode = tab === 'text';
                document.getElementById('imageSource').style.display = isTextMode ? 'none' : 'block';
                document.getElementById('textSource').style.display = isTextMode ? 'block' : 'none';
                document.getElementById('imageTabBtn').classList.toggle('active', !isTextMode);
                document.getElementById('textTabBtn').classList.toggle('active', isTextMode);
                
                if (isTextMode) {
                    document.getElementById('api').checked = true;
                    toggleProcessingMethod();
                    document.getElementById('local').disabled = true;
                    document.getElementById('generateBtn').disabled = false;
                } else {
                    document.getElementById('local').disabled = false;
                    document.getElementById('generateBtn').disabled = !selectedFile;
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
                const isTextMode = document.getElementById('textSource').style.display !== 'none';
                
  if (isTextMode) {
    const prompt = document.getElementById('textPrompt').value.trim();
    if (!prompt) {
      alert('Please enter a text prompt');
      return;
    }

    // Validate Tripo3D API key for text-to-3D
    const apiToken = document.getElementById('apiToken').value.trim();
    if (!apiToken) {
      alert('Please enter an API token');
      return;
    }
    if (apiToken.includes(':')) {
      const msg = 'Text-to-3D requires a different Cloud API key type (format: tsk_...)\\n\\n' +
                  'Your current key appears to be for image-to-3D only.\\n' +
                  'Please obtain a compatible Cloud API key.';
      alert(msg);
      return;
    }

    const formData = new FormData();
    formData.append('prompt', prompt);
    formData.append('negative_prompt', document.getElementById('negativePrompt').value.trim());
    formData.append('api_token', apiToken);
    formData.append('api_format', document.getElementById('apiFormat').value);

    document.getElementById('generateBtn').disabled = true;
                    startTime = Date.now();
                    logStartTime = Date.now();
                    logEntries = [];
                    lastLogIndex = 0;
                    document.getElementById('activityLog').innerHTML = '';
                    
                    addLogEntry('🚀 Starting text-to-3D generation...');
                    addLogEntry(`   Prompt: ${prompt}`);
                    updateProgress(0, 'Starting text-to-3D...');
                    
                    try {
                        const response = await fetch('/generate-text', {
                            method: 'POST',
                            body: formData
                        });
                        
                        if (!response.ok) {
                            throw new Error('Request failed');
                        }
                        
                        const data = await response.json();
                        jobId = data.job_id;
                        pollJob();
                    } catch (err) {
                        addLogEntry(`❌ Error: ${err.message}`);
                        document.getElementById('statusText').textContent = '❌ Failed';
                        document.getElementById('statusText').style.color = '#ef4444';
                        document.getElementById('generateBtn').disabled = false;
                    }
                    return;
                }
                
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
                lastLogIndex = 0;
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
                        
                        if (data.progress_log && data.progress_log.length > lastLogIndex) {
                            for (let i = lastLogIndex; i < data.progress_log.length; i++) {
                                addLogEntry(data.progress_log[i].msg);
                            }
                            lastLogIndex = data.progress_log.length;
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
                lastLogIndex = 0;
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
                document.getElementById('textPrompt').value = '';
                document.getElementById('negativePrompt').value = '';
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
                lastLogIndex = 0;
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


@app.post("/generate-text")
async def generate_from_text(
    request: Request,
    prompt: str = Form(...),
    negative_prompt: str = Form(""),
    api_token: Optional[str] = Form(None),
    api_format: Optional[str] = Form("glb"),
):
    """Start a text-to-3D generation job."""
    _prune_jobs()

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id,
        "status": "queued",
        "input_path": None,
        "mode": "text",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "api_token": api_token,
        "api_format": api_format,
        "created_at": time.time(),
        "updated_at": time.time(),
        "progress_percent": 0,
        "current_stage_msg": "Initializing text-to-3D...",
        "progress_log": [],
        "result": None,
    }

    asyncio.create_task(_process_text_job(job_id))
    return {"job_id": job_id}


async def _process_text_job(job_id: str):
    """Process a text-to-3D job asynchronously."""
    job = JOBS[job_id]
    job["status"] = "running"

    def progress_callback(stage, pct, msg):
        job["progress_percent"] = pct
        job["current_stage_msg"] = msg
        job["progress_log"].append({"stage": stage, "msg": msg, "ts": time.time()})
        job["updated_at"] = time.time()

    try:
        from core.unified_api import Unified3DAPI, APICredentials

        creds = (
            APICredentials.from_string(job["api_token"]) if job["api_token"] else None
        )
        api = Unified3DAPI(credentials=creds)

        result = await api.generate_from_text(
            prompt=job["prompt"],
            negative_prompt=job["negative_prompt"],
            format_type=job["api_format"],
            progress_callback=lambda pct, msg: progress_callback("generate", pct, msg),
        )

        if result.success:
            output_files = {}
            if result.model_path:
                ext = os.path.splitext(result.model_path)[1].lstrip(".")
                filename = os.path.basename(result.model_path)
                output_files[ext] = f"/output/{filename}"
            job["result"] = output_files
            job["status"] = "done"
        else:
            job["result"] = {"error": result.error_message or "Text-to-3D failed"}
            job["status"] = "error"
    except Exception as e:
        job["result"] = {"error": str(e)}
        job["status"] = "error"

    job["updated_at"] = time.time()


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
            web_result = {}
            for key, path in result.items():
                if isinstance(path, str):
                    # Try to convert file paths to web-accessible URLs
                    if os.path.isfile(path):
                        filename = os.path.basename(path)
                        web_result[key] = f"/output/{filename}"
                    elif os.path.exists(path):
                        # File exists but check failed - use anyway
                        filename = os.path.basename(path)
                        web_result[key] = f"/output/{filename}"
                    else:
                        web_result[key] = path
                else:
                    web_result[key] = path
            job["result"] = web_result
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


@app.get("/auto-credentials")
async def get_auto_credentials():
    """Fetch API credentials automatically from Supabase and local storage."""
    try:
        # Try to get credentials from Supabase (requires valid license)
        credentials = resolve_hitem3d_credentials(None)

        # If Supabase returned credentials, use them
        if credentials.get("access_token"):
            return {
                "token": credentials["access_token"],
                "source": "supabase",
                "success": True,
            }
        elif credentials.get("client_id") and credentials.get("client_secret"):
            return {
                "token": f"{credentials['client_id']}:{credentials['client_secret']}",
                "source": "supabase",
                "success": True,
            }

        # Fallback: Check local saved credentials
        saved = load_saved_api_credentials()
        if saved and saved.get("token"):
            return {"token": saved["token"], "source": "local", "success": True}

        return {"token": None, "source": None, "success": False}
    except Exception as e:
        return {"token": None, "source": None, "success": False, "error": str(e)}


@app.post("/hitem3d/balance")
async def check_balance(api_token: Optional[str] = Form(None)):
    """Check Hitem3D API balance."""
    try:
        credentials = resolve_hitem3d_credentials(api_token)
        result = await get_hitem3d_balance(api_token or None)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/save-credentials")
async def save_credentials(api_token: str = Form(...)):
    """Save API credentials to local storage."""
    try:
        token = api_token.strip()
        if not token:
            return {"success": False, "error": "Empty token"}

        # save_hitem3d_credentials handles both formats internally
        save_hitem3d_credentials(token)

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════
# ADMIN DASHBOARD — License-gated admin panel
# ═══════════════════════════════════════════════════════════════════

ADMIN_SESSION_COOKIE = "imagetoad_admin"
ADMIN_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _create_admin_session(user_id: int, username: str) -> str:
    """Create admin session token."""
    token = str(uuid.uuid4())
    ADMIN_SESSIONS[token] = {
        "user_id": user_id,
        "username": username,
        "created_at": time.time(),
    }
    return token


def _verify_admin_session(token: str) -> Optional[Dict[str, Any]]:
    """Verify admin session and return session data."""
    if not token:
        return None
    session = ADMIN_SESSIONS.get(token)
    if not session:
        return None
    if time.time() - session["created_at"] > SESSION_MAX_AGE:
        ADMIN_SESSIONS.pop(token, None)
        return None
    return session


async def require_admin(request: Request) -> Dict[str, Any]:
    """Dependency: require valid admin session."""
    token = request.cookies.get(ADMIN_SESSION_COOKIE)
    session = _verify_admin_session(token or "")
    if not session:
        raise HTTPException(status_code=401, detail="Admin authentication required")
    if not is_user_admin(session["user_id"]):
        raise HTTPException(status_code=403, detail="Admin access required")
    return session


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page():
    """Render admin login page."""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Login - Image → 3D Pro</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body {
                font-family: "Segoe UI", system-ui, sans-serif;
                background-color: #0a0a0a;
                color: #e5e7eb;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }
            .login-card {
                background: linear-gradient(135deg, #161616, #1a1a2e);
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 40px;
                width: 100%;
                max-width: 420px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.4);
            }
            h1 { color: #f59e0b; font-size: 22px; margin-bottom: 8px; text-align: center; }
            .subtitle { color: #64748b; font-size: 13px; text-align: center; margin-bottom: 28px; }
            label { display: block; color: #94a3b8; font-size: 12px; font-weight: 600; margin-bottom: 6px; text-transform: uppercase; }
            input {
                width: 100%;
                padding: 12px 16px;
                margin-bottom: 18px;
                border: 1px solid #334155;
                border-radius: 8px;
                background-color: #0f172a;
                color: #e5e7eb;
                font-size: 14px;
                transition: border-color 0.2s;
            }
            input:focus { outline: none; border-color: #f59e0b; }
            button {
                width: 100%;
                padding: 14px;
                background: linear-gradient(135deg, #f59e0b, #d97706);
                border: none;
                border-radius: 8px;
                color: #0a0a0a;
                font-weight: 700;
                font-size: 15px;
                cursor: pointer;
                transition: filter 0.2s;
            }
            button:hover { filter: brightness(1.1); }
            .error { color: #ef4444; font-size: 13px; margin-bottom: 16px; text-align: center; }
            .back-link { display: block; text-align: center; margin-top: 20px; color: #64748b; font-size: 12px; text-decoration: none; }
            .back-link:hover { color: #94a3b8; }
        </style>
    </head>
    <body>
        <div class="login-card">
            <h1>🔐 Admin Control Panel</h1>
            <p class="subtitle">Sign in with your admin credentials</p>
            <form method="POST" action="/admin/login">
                <label>Username</label>
                <input type="text" name="username" placeholder="Admin username" required />
                <label>Password</label>
                <input type="password" name="password" placeholder="Admin password" required />
                <label>License Key</label>
                <input type="text" name="license_key" placeholder="I3D-ADMIN-XXXX-XXXX" required />
                <button type="submit">🔓 Sign In as Admin</button>
            </form>
            <a href="/" class="back-link">← Back to main app</a>
        </div>
    </body>
    </html>
    """)


@app.post("/admin/login")
async def admin_do_login(
    username: str = Form(...),
    password: str = Form(...),
    license_key: str = Form(...),
):
    """Handle admin login."""
    # Verify credentials
    user_id = verify_user(username, password)
    if not user_id:
        return HTMLResponse(
            content="<script>alert('Invalid username or password'); window.location.href='/admin/login';</script>",
            status_code=401,
        )

    # Verify license key is an admin license
    license_key = license_key.strip().upper()
    if not license_key.startswith("I3D-ADMIN-"):
        return HTMLResponse(
            content="<script>alert('Invalid admin license key. Must start with I3D-ADMIN-'); window.location.href='/admin/login';</script>",
            status_code=401,
        )

    # Activate license and promote to admin if needed
    db_add_user_license(user_id, license_key, plan_id="admin", credits=999999)

    # Verify admin status
    if not is_user_admin(user_id):
        return HTMLResponse(
            content="<script>alert('Account does not have admin privileges'); window.location.href='/admin/login';</script>",
            status_code=403,
        )

    # Create admin session
    token = _create_admin_session(user_id, username)
    response = RedirectResponse(url="/admin", status_code=302)
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/admin/logout")
async def admin_logout():
    """Admin logout."""
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie(ADMIN_SESSION_COOKIE)
    return response


def _admin_dashboard_html(username: str) -> str:
    """Return admin dashboard HTML with full CRUD capabilities."""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Admin Dashboard - Image → 3D Pro</title>
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: "Segoe UI", "Inter", system-ui, sans-serif;
                background-color: #0a0a0a;
                color: #e5e7eb;
                min-height: 100vh;
            }}
            .topbar {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 16px 24px;
                background: linear-gradient(90deg, #1a1a2e, #16213e);
                border-bottom: 1px solid #334155;
            }}
            .topbar-left {{
                display: flex;
                align-items: center;
                gap: 16px;
            }}
            .topbar h1 {{
                font-size: 18px;
                color: #f59e0b;
            }}
            .topbar .badge {{
                background: rgba(245, 158, 11, 0.2);
                color: #f59e0b;
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 600;
            }}
            .topbar-right {{
                display: flex;
                align-items: center;
                gap: 16px;
                font-size: 13px;
                color: #94a3b8;
            }}
            .topbar-right a {{
                color: #60a5fa;
                text-decoration: none;
                font-size: 13px;
            }}
            .topbar-right a:hover {{ color: #93c5fd; }}

            .tabs {{
                display: flex;
                gap: 0;
                background: #111;
                border-bottom: 1px solid #1e293b;
            }}
            .tab {{
                padding: 12px 24px;
                cursor: pointer;
                color: #64748b;
                font-size: 13px;
                font-weight: 600;
                border-bottom: 2px solid transparent;
                transition: all 0.2s;
            }}
            .tab:hover {{ color: #e5e7eb; }}
            .tab.active {{
                color: #f59e0b;
                border-bottom-color: #f59e0b;
                background: rgba(245, 158, 11, 0.05);
            }}
            .tab-content {{
                display: none;
                padding: 24px;
            }}
            .tab-content.active {{ display: block; }}

            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 16px;
                margin-bottom: 24px;
            }}
            .stat-card {{
                background: #161616;
                border: 1px solid #1e293b;
                border-radius: 10px;
                padding: 20px;
            }}
            .stat-label {{
                color: #64748b;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                margin-bottom: 8px;
            }}
            .stat-value {{
                color: #e5e7eb;
                font-size: 28px;
                font-weight: 700;
            }}
            .stat-value.highlight {{ color: #f59e0b; }}

            table {{
                width: 100%;
                border-collapse: collapse;
                background: #161616;
                border-radius: 10px;
                overflow: hidden;
                border: 1px solid #1e293b;
            }}
            th {{
                background: #1e293b;
                color: #94a3b8;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                padding: 12px 16px;
                text-align: left;
            }}
            td {{
                padding: 12px 16px;
                border-top: 1px solid #1e293b;
                font-size: 13px;
                color: #e5e7eb;
            }}
            tr:hover {{ background: rgba(245, 158, 11, 0.03); }}

            .toggle-switch {{
                position: relative;
                width: 44px;
                height: 24px;
                cursor: pointer;
            }}
            .toggle-switch input {{
                opacity: 0;
                width: 0;
                height: 0;
            }}
            .slider {{
                position: absolute;
                inset: 0;
                background: #334155;
                border-radius: 12px;
                transition: 0.3s;
            }}
            .slider::before {{
                content: '';
                position: absolute;
                width: 18px;
                height: 18px;
                left: 3px;
                bottom: 3px;
                background: white;
                border-radius: 50%;
                transition: 0.3s;
            }}
            .toggle-switch input:checked + .slider {{
                background: #22c55e;
            }}
            .toggle-switch input:checked + .slider::before {{
                transform: translateX(20px);
            }}

            .btn {{
                padding: 6px 14px;
                border-radius: 6px;
                border: 1px solid #334155;
                background: #1e293b;
                color: #e5e7eb;
                font-size: 12px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.15s;
                margin: 2px;
            }}
            .btn:hover {{ background: #334155; border-color: #60a5fa; }}
            .btn-danger {{ background: rgba(239, 68, 68, 0.2); border-color: rgba(239, 68, 68, 0.5); color: #fca5a5; }}
            .btn-danger:hover {{ background: rgba(239, 68, 68, 0.3); }}
            .btn-success {{ background: rgba(34, 197, 94, 0.2); border-color: rgba(34, 197, 94, 0.5); color: #86efac; }}
            .btn-success:hover {{ background: rgba(34, 197, 94, 0.3); }}
            .btn-primary {{ background: rgba(59, 130, 246, 0.2); border-color: rgba(59, 130, 246, 0.5); color: #93c5fd; }}
            .btn-primary:hover {{ background: rgba(59, 130, 246, 0.3); }}
            .btn-warn {{ background: rgba(245, 158, 11, 0.2); border-color: rgba(245, 158, 11, 0.5); color: #fcd34d; }}
            .btn-warn:hover {{ background: rgba(245, 158, 11, 0.3); }}
            .section-title {{ color: #f59e0b; font-size: 16px; font-weight: 700; margin-bottom: 16px; }}
            .badge-admin {{ background: rgba(245, 158, 11, 0.2); color: #f59e0b; padding: 2px 8px; border-radius: 4px; font-size: 10px; }}
            .badge-user {{ background: rgba(96, 165, 250, 0.2); color: #60a5fa; padding: 2px 8px; border-radius: 4px; font-size: 10px; }}
            .badge-active {{ background: rgba(34, 197, 94, 0.2); color: #22c55e; padding: 2px 8px; border-radius: 4px; font-size: 10px; }}
            .loading {{ color: #64748b; font-size: 13px; padding: 20px; text-align: center; }}
            .toolbar {{ display: flex; gap: 12px; margin-bottom: 16px; align-items: center; }}

            /* Modal */
            .modal-overlay {{
                display: none;
                position: fixed;
                inset: 0;
                background: rgba(0,0,0,0.7);
                z-index: 1000;
                justify-content: center;
                align-items: center;
            }}
            .modal-overlay.active {{ display: flex; }}
            .modal {{
                background: #1a1a2e;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 28px;
                width: 100%;
                max-width: 560px;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: 0 16px 48px rgba(0,0,0,0.5);
            }}
            .modal h2 {{
                color: #f59e0b;
                font-size: 18px;
                margin-bottom: 20px;
            }}
            .modal label {{
                display: block;
                color: #94a3b8;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                margin-bottom: 4px;
                margin-top: 12px;
            }}
            .modal input, .modal select {{
                width: 100%;
                padding: 10px 14px;
                border: 1px solid #334155;
                border-radius: 6px;
                background: #0f172a;
                color: #e5e7eb;
                font-size: 13px;
            }}
            .modal input:focus, .modal select:focus {{ outline: none; border-color: #f59e0b; }}
            .modal-actions {{
                display: flex;
                gap: 12px;
                margin-top: 20px;
                justify-content: flex-end;
            }}
            .license-row {{
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 8px;
                background: #0f172a;
                border-radius: 6px;
                margin-bottom: 6px;
                font-size: 12px;
            }}
            .license-row .key {{ color: #fcd34d; flex: 1; font-family: monospace; }}
            .license-row .plan {{ color: #60a5fa; }}
            .license-row .credits {{ color: #86efac; }}
            .empty-state {{ color: #64748b; font-size: 13px; text-align: center; padding: 30px; }}
        </style>
    </head>
    <body>
        <div class="topbar">
            <div class="topbar-left">
                <h1>⚙️ Admin Control Panel</h1>
                <span class="badge">v{APP_WEB_VERSION}</span>
            </div>
            <div class="topbar-right">
                <span>👤 {username}</span>
                <a href="/">← Main App</a>
                <a href="/admin/logout">Logout</a>
            </div>
        </div>

        <div class="tabs">
            <div class="tab active" onclick="switchTab('users', this)">👥 Users</div>
            <div class="tab" onclick="switchTab('licenses', this)">🔑 Licenses</div>
            <div class="tab" onclick="switchTab('models', this)">📦 Models</div>
            <div class="tab" onclick="switchTab('stats', this)">📊 Analytics</div>
        </div>

        <!-- Users Tab -->
        <div id="tab-users" class="tab-content active">
            <div class="toolbar">
                <div class="section-title">User Management</div>
                <div style="flex:1"></div>
                <button class="btn btn-success" onclick="showCreateUser()">➕ Create User</button>
                <button class="btn" onclick="loadUsers()">🔄 Refresh</button>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Username</th>
                        <th>Role</th>
                        <th>Created</th>
                        <th>Gens Used</th>
                        <th>Remaining</th>
                        <th>License</th>
                        <th>Credits</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="userTableBody">
                    <tr><td colspan="9" class="loading">Loading users...</td></tr>
                </tbody>
            </table>
        </div>

        <!-- Licenses Tab -->
        <div id="tab-licenses" class="tab-content">
            <div class="toolbar">
                <div class="section-title">License Key Management</div>
                <div style="flex:1"></div>
                <button class="btn" onclick="loadLicenses()">🔄 Refresh</button>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>User</th>
                        <th>License Key</th>
                        <th>Plan</th>
                        <th>Credits</th>
                        <th>Activated</th>
                        <th>Expires</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="licenseTableBody">
                    <tr><td colspan="7" class="loading">Loading licenses...</td></tr>
                </tbody>
            </table>
        </div>

        <!-- Models Tab -->
        <div id="tab-models" class="tab-content">
            <div class="section-title">Cloud Model Configuration</div>
            <table>
                <thead>
                    <tr>
                        <th>Model</th>
                        <th>Provider</th>
                        <th>Enabled</th>
                        <th>Image→3D</th>
                        <th>Text→3D</th>
                        <th>Formats</th>
                    </tr>
                </thead>
                <tbody id="modelTableBody">
                    <tr><td colspan="6" class="loading">Loading models...</td></tr>
                </tbody>
            </table>
            <div style="margin-top: 16px; display: flex; gap: 12px;">
                <button class="btn btn-success" onclick="saveModelConfig()">💾 Save Changes</button>
                <button class="btn" onclick="loadModels()">🔄 Refresh</button>
            </div>

            <!-- API Keys & Credits Section -->
            <div class="section-title" style="margin-top:32px;">🔑 API Keys &amp; Credits (Stored in Supabase)</div>
            <div id="apiKeysContainer" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(460px,1fr));gap:16px;">
                <div class="loading">Loading API keys...</div>
            </div>
        </div>

        <!-- Stats Tab -->
        <div id="tab-stats" class="tab-content">
            <div class="section-title">Usage Analytics</div>
            <div class="stats-grid" id="statsGrid">
                <div class="stat-card"><div class="stat-label">Total Users</div><div class="stat-value" id="statUsers">--</div></div>
                <div class="stat-card"><div class="stat-label">Total Generations</div><div class="stat-value highlight" id="statGens">--</div></div>
                <div class="stat-card"><div class="stat-label">Active Licenses</div><div class="stat-value" id="statLicenses">--</div></div>
                <div class="stat-card"><div class="stat-label">Admin Users</div><div class="stat-value" id="statAdmins">--</div></div>
            </div>
        </div>

        <!-- Modal Overlay -->
        <div class="modal-overlay" id="modalOverlay" onclick="if(event.target===this)closeModal()">
            <div class="modal" id="modalContent"></div>
        </div>

        <script>
            // ── Tab switching ──────────────────────────────
            function switchTab(name, el) {{
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                document.getElementById('tab-' + name).classList.add('active');
                if (el) el.classList.add('active');

                if (name === 'models') loadModels();
                if (name === 'users') loadUsers();
                if (name === 'stats') loadStats();
                if (name === 'licenses') loadLicenses();
            }}

            // ── Modal helpers ──────────────────────────────
            function openModal(html) {{
                document.getElementById('modalContent').innerHTML = html;
                document.getElementById('modalOverlay').classList.add('active');
            }}
            function closeModal() {{
                document.getElementById('modalOverlay').classList.remove('active');
            }}

            // ── Users ──────────────────────────────────────
            async function loadUsers() {{
                try {{
                    const r = await fetch('/admin/api/users');
                    const data = await r.json();
                    const tbody = document.getElementById('userTableBody');
                    if (!data.users || data.users.length === 0) {{
                        tbody.innerHTML = '<tr><td colspan="9" class="loading">No users found</td></tr>';
                        return;
                    }}
                    tbody.innerHTML = data.users.map(u => `
                        <tr>
                            <td>${{u.id}}</td>
                            <td>${{u.username}}</td>
                            <td>${{u.is_admin ? '<span class="badge-admin">Admin</span>' : '<span class="badge-user">User</span>'}}</td>
                            <td>${{(u.created_at || '').substring(0, 10)}}</td>
                            <td>${{u.generations_used || 0}}</td>
                            <td>${{u.generations_remaining || 0}}</td>
                            <td>${{u.plan_id || 'None'}}</td>
                            <td>${{u.credits || 0}}</td>
                            <td>
                                <button class="btn btn-primary" onclick="showUserDetail(${{u.id}})">📋 Detail</button>
                                <button class="btn" onclick="showEditUser(${{u.id}}, '${{u.username}}', ${{u.is_admin}})">✏️</button>
                                <button class="btn btn-warn" onclick="resetTrial(${{u.id}})">🔄</button>
                                <button class="btn btn-success" onclick="showAddLicense(${{u.id}}, '${{u.username}}')">🔑</button>
                                <button class="btn" onclick="showUpdateCredits(${{u.id}}, '${{u.username}}', ${{u.credits || 0}})">💰</button>
                                ${{!u.is_admin ? `<button class="btn btn-danger" onclick="deleteUser(${{u.id}})">🗑️</button>` : ''}}
                            </td>
                        </tr>
                    `).join('');
                }} catch (e) {{
                    document.getElementById('userTableBody').innerHTML = '<tr><td colspan="9" class="loading">Failed to load users</td></tr>';
                }}
            }}

            // ── Create User ────────────────────────────────
            function showCreateUser() {{
                openModal(`
                    <h2>➕ Create New User</h2>
                    <label>Username</label>
                    <input type="text" id="newUsername" placeholder="Enter username" />
                    <label>Password</label>
                    <input type="password" id="newPassword" placeholder="Enter password" />
                    <label>Role</label>
                    <select id="newRole">
                        <option value="user">User</option>
                        <option value="admin">Admin</option>
                    </select>
                    <div class="modal-actions">
                        <button class="btn" onclick="closeModal()">Cancel</button>
                        <button class="btn btn-success" onclick="createUser()">Create User</button>
                    </div>
                `);
            }}
            async function createUser() {{
                const username = document.getElementById('newUsername').value.trim();
                const password = document.getElementById('newPassword').value;
                const role = document.getElementById('newRole').value;
                if (!username || !password) {{ alert('Username and password are required'); return; }}
                try {{
                    const r = await fetch('/admin/api/users', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ username, password, is_admin: role === 'admin' }})
                    }});
                    const data = await r.json();
                    if (data.success) {{ closeModal(); loadUsers(); alert('✅ User created!'); }}
                    else alert('❌ ' + (data.error || 'Failed'));
                }} catch(e) {{ alert('Error: ' + e); }}
            }}

            // ── Edit User ──────────────────────────────────
            function showEditUser(id, username, isAdmin) {{
                openModal(`
                    <h2>✏️ Edit User #${{id}}</h2>
                    <label>Username</label>
                    <input type="text" id="editUsername" value="${{username}}" />
                    <label>New Password (leave blank to keep)</label>
                    <input type="password" id="editPassword" placeholder="Leave blank to keep current" />
                    <label>Role</label>
                    <select id="editRole">
                        <option value="user" ${{!isAdmin ? 'selected' : ''}}>User</option>
                        <option value="admin" ${{isAdmin ? 'selected' : ''}}>Admin</option>
                    </select>
                    <div class="modal-actions">
                        <button class="btn" onclick="closeModal()">Cancel</button>
                        <button class="btn btn-primary" onclick="updateUser(${{id}})">Save Changes</button>
                    </div>
                `);
            }}
            async function updateUser(id) {{
                const body = {{}};
                const un = document.getElementById('editUsername').value.trim();
                const pw = document.getElementById('editPassword').value;
                const role = document.getElementById('editRole').value;
                if (un) body.username = un;
                if (pw) body.password = pw;
                body.is_admin = role === 'admin';
                try {{
                    const r = await fetch('/admin/api/users/' + id, {{
                        method: 'PUT',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify(body)
                    }});
                    const data = await r.json();
                    if (data.success) {{ closeModal(); loadUsers(); alert('✅ User updated!'); }}
                    else alert('❌ ' + (data.error || 'Failed'));
                }} catch(e) {{ alert('Error: ' + e); }}
            }}

            // ── User Detail (all licenses, trial info) ────
            async function showUserDetail(id) {{
                try {{
                    const r = await fetch('/admin/api/users/' + id + '/detail');
                    const u = await r.json();
                    if (u.error) {{ alert(u.error); return; }}

                    let licensesHtml = '<div class="empty-state">No licenses</div>';
                    if (u.licenses && u.licenses.length > 0) {{
                        licensesHtml = u.licenses.map(l => `
                            <div class="license-row">
                                <span class="key">${{l.license_key}}</span>
                                <span class="plan">${{l.plan_id}}</span>
                                <span class="credits">${{l.credits}} credits</span>
                                <span style="color:#64748b;font-size:11px">${{(l.activated_at||'').substring(0,10)}}</span>
                                <button class="btn btn-danger" onclick="revokeLicense(${{l.id}}, ${{id}})" style="padding:3px 8px;font-size:11px">Revoke</button>
                            </div>
                        `).join('');
                    }}

                    openModal(`
                        <h2>📋 User Detail: ${{u.username}}</h2>
                        <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px;">
                            <div class="stat-card" style="padding:12px">
                                <div class="stat-label">Role</div>
                                <div style="font-size:16px;font-weight:700">${{u.is_admin ? '🔶 Admin' : '🔵 User'}}</div>
                            </div>
                            <div class="stat-card" style="padding:12px">
                                <div class="stat-label">Created</div>
                                <div style="font-size:16px;font-weight:700">${{(u.created_at||'').substring(0,10)}}</div>
                            </div>
                            <div class="stat-card" style="padding:12px">
                                <div class="stat-label">Generations Used</div>
                                <div style="font-size:16px;font-weight:700">${{u.trial ? u.trial.generations_used : 0}}</div>
                            </div>
                            <div class="stat-card" style="padding:12px">
                                <div class="stat-label">Remaining</div>
                                <div style="font-size:16px;font-weight:700">${{u.trial ? u.trial.generations_remaining : 0}}</div>
                            </div>
                        </div>
                        <div class="section-title" style="font-size:14px">🔑 Licenses</div>
                        ${{licensesHtml}}
                        <div class="modal-actions">
                            <button class="btn btn-success" onclick="closeModal(); showAddLicense(${{u.id}}, '${{u.username}}')">➕ Add License</button>
                            <button class="btn" onclick="closeModal()">Close</button>
                        </div>
                    `);
                }} catch(e) {{ alert('Error: ' + e); }}
            }}

            // ── Add License ────────────────────────────────
            function showAddLicense(userId, username) {{
                openModal(`
                    <h2>🔑 Add License for ${{username}}</h2>
                    <label>License Key</label>
                    <input type="text" id="licKey" placeholder="e.g. I3D-PRO-XXXXXX" />
                    <label>Plan</label>
                    <select id="licPlan">
                        <option value="pro">Pro</option>
                        <option value="enterprise">Enterprise</option>
                        <option value="admin">Admin</option>
                        <option value="free">Free Trial</option>
                    </select>
                    <label>Credits</label>
                    <input type="number" id="licCredits" value="300" min="0" />
                    <label>Expires At (optional)</label>
                    <input type="date" id="licExpires" />
                    <div class="modal-actions">
                        <button class="btn" onclick="closeModal()">Cancel</button>
                        <button class="btn btn-success" onclick="addLicense(${{userId}})">Add License</button>
                    </div>
                `);
            }}
            async function addLicense(userId) {{
                const key = document.getElementById('licKey').value.trim();
                const plan = document.getElementById('licPlan').value;
                const credits = parseInt(document.getElementById('licCredits').value) || 0;
                const expires = document.getElementById('licExpires').value || null;
                if (!key) {{ alert('License key is required'); return; }}
                try {{
                    const r = await fetch('/admin/api/users/' + userId + '/licenses', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ license_key: key, plan_id: plan, credits, expires_at: expires }})
                    }});
                    const data = await r.json();
                    if (data.success) {{ closeModal(); loadUsers(); alert('✅ License added!'); }}
                    else alert('❌ ' + (data.error || 'Failed'));
                }} catch(e) {{ alert('Error: ' + e); }}
            }}

            // ── Revoke License ─────────────────────────────
            async function revokeLicense(licenseId, userId) {{
                if (!confirm('Revoke this license? This cannot be undone.')) return;
                try {{
                    const r = await fetch('/admin/api/licenses/' + licenseId, {{ method: 'DELETE' }});
                    const data = await r.json();
                    if (data.success) {{ showUserDetail(userId); alert('✅ License revoked'); }}
                    else alert('❌ ' + (data.error || 'Failed'));
                }} catch(e) {{ alert('Error: ' + e); }}
            }}

            // ── Update Credits ─────────────────────────────
            function showUpdateCredits(userId, username, currentCredits) {{
                openModal(`
                    <h2>💰 Update Credits: ${{username}}</h2>
                    <label>New Credit Amount</label>
                    <input type="number" id="newCredits" value="${{currentCredits}}" min="0" />
                    <div class="modal-actions">
                        <button class="btn" onclick="closeModal()">Cancel</button>
                        <button class="btn btn-primary" onclick="saveCredits(${{userId}})">Save</button>
                    </div>
                `);
            }}
            async function saveCredits(userId) {{
                const credits = parseInt(document.getElementById('newCredits').value) || 0;
                try {{
                    const r = await fetch('/admin/api/users/' + userId + '/credits', {{
                        method: 'PUT',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ credits }})
                    }});
                    const data = await r.json();
                    if (data.success) {{ closeModal(); loadUsers(); alert('✅ Credits updated!'); }}
                    else alert('❌ ' + (data.error || 'Failed'));
                }} catch(e) {{ alert('Error: ' + e); }}
            }}

            // ── Reset Trial ────────────────────────────────
            async function resetTrial(userId) {{
                if (!confirm('Reset trial for user ' + userId + '?')) return;
                try {{
                    const r = await fetch('/admin/api/users/' + userId + '/reset-trial', {{ method: 'POST' }});
                    const data = await r.json();
                    if (data.success) loadUsers();
                    else alert('Failed: ' + (data.error || 'Unknown error'));
                }} catch (e) {{ alert('Error: ' + e); }}
            }}

            // ── Delete User ────────────────────────────────
            async function deleteUser(userId) {{
                if (!confirm('Delete user ' + userId + '? This cannot be undone.')) return;
                try {{
                    const r = await fetch('/admin/api/users/' + userId, {{ method: 'DELETE' }});
                    const data = await r.json();
                    if (data.success) loadUsers();
                    else alert('Failed: ' + (data.error || 'Unknown error'));
                }} catch (e) {{ alert('Error: ' + e); }}
            }}

            // ── Licenses Tab ───────────────────────────────
            async function loadLicenses() {{
                try {{
                    const r = await fetch('/admin/api/licenses');
                    const data = await r.json();
                    const tbody = document.getElementById('licenseTableBody');
                    if (!data.licenses || data.licenses.length === 0) {{
                        tbody.innerHTML = '<tr><td colspan="7" class="loading">No licenses found</td></tr>';
                        return;
                    }}
                    tbody.innerHTML = data.licenses.map(l => `
                        <tr>
                            <td>${{l.username}} (ID: ${{l.user_id}})</td>
                            <td style="font-family:monospace;color:#fcd34d">${{l.license_key}}</td>
                            <td><span class="badge-active">${{l.plan_id}}</span></td>
                            <td>${{l.credits}}</td>
                            <td>${{(l.activated_at||'').substring(0,10)}}</td>
                            <td>${{l.expires_at ? l.expires_at.substring(0,10) : 'Never'}}</td>
                            <td>
                                <button class="btn btn-danger" onclick="revokeLicenseReload(${{l.id}})">Revoke</button>
                            </td>
                        </tr>
                    `).join('');
                }} catch(e) {{
                    document.getElementById('licenseTableBody').innerHTML = '<tr><td colspan="7" class="loading">Failed to load</td></tr>';
                }}
            }}
            async function revokeLicenseReload(licenseId) {{
                if (!confirm('Revoke this license?')) return;
                try {{
                    const r = await fetch('/admin/api/licenses/' + licenseId, {{ method: 'DELETE' }});
                    const data = await r.json();
                    if (data.success) {{ loadLicenses(); alert('✅ Revoked'); }}
                    else alert('❌ ' + (data.error || 'Failed'));
                }} catch(e) {{ alert('Error: ' + e); }}
            }}

            // ── Models ─────────────────────────────────────
            async function loadModels() {{
                try {{
                    const r = await fetch('/admin/api/models');
                    const data = await r.json();
                    const tbody = document.getElementById('modelTableBody');
                    if (!data.models || data.models.length === 0) {{
                        tbody.innerHTML = '<tr><td colspan="6" class="loading">No models configured</td></tr>';
                        return;
                    }}
                    tbody.innerHTML = data.models.map(m => `
                        <tr>
                            <td>${{m.model_name}}</td>
                            <td>${{m.provider}}</td>
                            <td>
                                <label class="toggle-switch">
                                    <input type="checkbox" data-model="${{m.model_id}}" ${{m.is_enabled ? 'checked' : ''}} />
                                    <span class="slider"></span>
                                </label>
                            </td>
                            <td>${{m.supports_image_to_3d ? '✅' : '❌'}}</td>
                            <td>${{m.supports_text_to_3d ? '✅' : '❌'}}</td>
                            <td>${{(m.output_formats || []).join(', ')}}</td>
                        </tr>
                    `).join('');
                }} catch (e) {{
                    document.getElementById('modelTableBody').innerHTML = '<tr><td colspan="6" class="loading">Failed to load models</td></tr>';
                }}
                // Also load API keys section
                loadApiKeys();
            }}

            async function saveModelConfig() {{
                const toggles = document.querySelectorAll('#modelTableBody input[type="checkbox"]');
                const updates = [];
                toggles.forEach(t => {{
                    updates.push({{ model_id: t.dataset.model, is_enabled: t.checked }});
                }});
                try {{
                    const r = await fetch('/admin/api/models', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ updates }})
                    }});
                    const data = await r.json();
                    alert(data.success ? '✅ Model config saved!' : '❌ Failed to save');
                }} catch (e) {{
                    alert('❌ Error saving config');
                }}
            }}

            // ── API Keys & Credits ────────────────────────────
            const MODEL_LABELS = {{
                'tripo3d': '🔷 Tripo3D',
                'hitem3d': '🟢 Hitem3D',
                'meshy_ai': '🟠 Meshy AI',
                'neural4d': '🟣 Neural4D',
            }};

            async function loadApiKeys() {{
                const container = document.getElementById('apiKeysContainer');
                try {{
                    const r = await fetch('/admin/api/model-keys');
                    const data = await r.json();
                    const keys = data.keys || [];
                    if (keys.length === 0) {{
                        container.innerHTML = '<div class="loading">No API keys configured yet.</div>';
                        return;
                    }}
                    // Group keys by model_id
                    const grouped = {{}};
                    keys.forEach(k => {{
                        if (!grouped[k.model_id]) grouped[k.model_id] = [];
                        grouped[k.model_id].push(k);
                    }});

                    container.innerHTML = Object.entries(grouped).map(([modelId, modelKeys]) => `
                        <div style="background:#1a1a2e;border:1px solid #333;border-radius:12px;padding:20px;">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
                                <span style="font-size:16px;font-weight:600;color:#e0e0e0;">${{MODEL_LABELS[modelId] || modelId}}</span>
                                <span style="font-size:12px;padding:4px 10px;border-radius:20px;background:${{modelKeys[0].remaining_credits > 0 ? '#1b5e20' : '#b71c1c'}};color:#fff;">
                                    ${{modelKeys[0].remaining_credits > 0 ? '✅ Active' : '⚠️ No Credits'}}
                                </span>
                            </div>
                            ${{modelKeys.map(k => `
                                <div style="background:#12121f;border-radius:8px;padding:14px;margin-bottom:10px;">
                                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                                        <span style="font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.5px;">🔑 ${{k.key_name}}</span>
                                    </div>
                                    <div style="display:flex;gap:8px;margin-bottom:10px;">
                                        <input type="password" id="key_${{k.model_id}}_${{k.key_name}}"
                                            placeholder="${{k.key_value_masked || 'Enter API key...'}}"
                                            style="flex:1;padding:8px 12px;border-radius:6px;border:1px solid #444;background:#0d0d1a;color:#ddd;font-family:monospace;font-size:13px;" />
                                        <button onclick="toggleKeyVisibility('key_${{k.model_id}}_${{k.key_name}}')" class="btn" style="padding:6px 10px;font-size:12px;">👁</button>
                                    </div>
                                    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:10px;">
                                        <div style="text-align:center;">
                                            <div style="font-size:10px;color:#888;text-transform:uppercase;">Total Credits</div>
                                            <input type="number" id="tc_${{k.model_id}}_${{k.key_name}}" value="${{k.total_credits || 0}}" min="0"
                                                style="width:100%;padding:6px;border-radius:4px;border:1px solid #444;background:#0d0d1a;color:#4fc3f7;font-size:14px;font-weight:600;text-align:center;" />
                                        </div>
                                        <div style="text-align:center;">
                                            <div style="font-size:10px;color:#888;text-transform:uppercase;">Used</div>
                                            <div style="padding:6px;color:#ef9a9a;font-size:14px;font-weight:600;">${{k.used_credits || 0}}</div>
                                        </div>
                                        <div style="text-align:center;">
                                            <div style="font-size:10px;color:#888;text-transform:uppercase;">Remaining</div>
                                            <div style="padding:6px;color:${{k.remaining_credits > 0 ? '#81c784' : '#ef5350'}};font-size:14px;font-weight:600;">${{k.remaining_credits || 0}}</div>
                                        </div>
                                    </div>
                                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
                                        <span style="font-size:11px;color:#888;">Trial Credits (per user):</span>
                                        <input type="number" id="trc_${{k.model_id}}_${{k.key_name}}" value="${{k.trial_credits || 0}}" min="0" max="10"
                                            style="width:60px;padding:4px 8px;border-radius:4px;border:1px solid #444;background:#0d0d1a;color:#ce93d8;font-size:13px;text-align:center;" />
                                    </div>
                                    <button onclick="saveApiKey('${{k.model_id}}','${{k.key_name}}')" class="btn btn-success" style="width:100%;padding:8px;font-size:13px;">💾 Save Key &amp; Credits</button>
                                </div>
                            `).join('')}}
                        </div>
                    `).join('');
                }} catch (e) {{
                    container.innerHTML = '<div class="loading">❌ Failed to load API keys: ' + e.message + '</div>';
                }}
            }}

            function toggleKeyVisibility(inputId) {{
                const input = document.getElementById(inputId);
                input.type = input.type === 'password' ? 'text' : 'password';
            }}

            async function saveApiKey(modelId, keyName) {{
                const keyInput = document.getElementById('key_' + modelId + '_' + keyName);
                const totalInput = document.getElementById('tc_' + modelId + '_' + keyName);
                const trialInput = document.getElementById('trc_' + modelId + '_' + keyName);

                const payload = {{
                    model_id: modelId,
                    key_name: keyName,
                    total_credits: parseInt(totalInput.value) || 0,
                    trial_credits: parseInt(trialInput.value) || 0,
                }};
                // Only send key_value if user actually typed something in
                if (keyInput.value.trim()) {{
                    payload.key_value = keyInput.value.trim();
                }}

                try {{
                    const r = await fetch('/admin/api/model-keys', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(payload)
                    }});
                    const data = await r.json();
                    if (data.success) {{
                        alert('✅ Saved ' + keyName + ' for ' + modelId);
                        keyInput.value = '';
                        loadApiKeys();
                    }} else {{
                        alert('❌ ' + (data.error || 'Failed to save'));
                    }}
                }} catch (e) {{
                    alert('❌ Error: ' + e.message);
                }}
            }}

            // ── Stats ──────────────────────────────────────
            async function loadStats() {{
                try {{
                    const r = await fetch('/admin/api/stats');
                    const data = await r.json();
                    document.getElementById('statUsers').textContent = data.total_users || 0;
                    document.getElementById('statGens').textContent = data.total_generations || 0;
                    document.getElementById('statLicenses').textContent = data.active_licenses || 0;
                    document.getElementById('statAdmins').textContent = data.admin_users || 0;
                }} catch (e) {{
                    console.error('Failed to load stats:', e);
                }}
            }}

            // Load initial data
            loadUsers();
        </script>
    </body>
    </html>
    """


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Render admin dashboard (requires admin session)."""
    token = request.cookies.get(ADMIN_SESSION_COOKIE)
    session = _verify_admin_session(token or "")
    if not session or not is_user_admin(session["user_id"]):
        return RedirectResponse(url="/admin/login", status_code=302)
    return HTMLResponse(content=_admin_dashboard_html(session["username"]))


@app.get("/admin/api/models")
async def admin_get_models(session: Dict = Depends(require_admin)):
    """Get all model configurations (admin only)."""
    try:
        from core.admin_manager import AdminModelManager
        mgr = AdminModelManager()
        models = mgr.get_all_models()
        return {"models": models}
    except Exception as e:
        return {"models": [], "error": str(e)}


@app.post("/admin/api/models")
async def admin_save_models(request: Request, session: Dict = Depends(require_admin)):
    """Save model configuration updates (admin only)."""
    try:
        from core.admin_manager import AdminModelManager
        mgr = AdminModelManager()
        body = await request.json()
        updates = body.get("updates", [])
        for update in updates:
            mgr.toggle_model(update["model_id"], update["is_enabled"])
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/admin/api/model-keys")
async def admin_get_model_keys(session: Dict = Depends(require_admin)):
    """Get all model API keys with masked values and credit info."""
    try:
        from core.admin_manager import AdminModelManager
        mgr = AdminModelManager()
        keys = mgr.get_model_api_keys()
        return {"keys": keys}
    except Exception as e:
        return {"keys": [], "error": str(e)}


@app.post("/admin/api/model-keys")
async def admin_save_model_key(request: Request, session: Dict = Depends(require_admin)):
    """Save or update API key and credits for a model."""
    try:
        from core.admin_manager import AdminModelManager
        mgr = AdminModelManager()
        body = await request.json()
        model_id = body.get("model_id")
        key_name = body.get("key_name")
        if not model_id or not key_name:
            return {"success": False, "error": "model_id and key_name required"}
        success = mgr.save_model_api_key(
            model_id=model_id,
            key_name=key_name,
            key_value=body.get("key_value"),
            total_credits=body.get("total_credits"),
            trial_credits=body.get("trial_credits"),
        )
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/admin/api/model-credits")
async def admin_get_model_credits(session: Dict = Depends(require_admin)):
    """Get credit summary for all models."""
    try:
        from core.admin_manager import AdminModelManager
        mgr = AdminModelManager()
        models = mgr.get_all_models()
        credits = {}
        for m in models:
            credits[m["model_id"]] = mgr.get_model_credits(m["model_id"])
        return {"credits": credits}
    except Exception as e:
        return {"credits": {}, "error": str(e)}


@app.get("/admin/api/users")
async def admin_get_users(session: Dict = Depends(require_admin)):
    """Get all users (admin only)."""
    try:
        users = get_all_users()
        return {"users": users}
    except Exception as e:
        return {"users": [], "error": str(e)}


@app.post("/admin/api/users")
async def admin_create_user(request: Request, session: Dict = Depends(require_admin)):
    """Create a new user (admin only)."""
    try:
        body = await request.json()
        username = body.get("username", "").strip()
        password = body.get("password", "")
        is_admin = body.get("is_admin", False)
        if not username or not password:
            return {"success": False, "error": "Username and password required"}
        success = create_user(username, password, is_admin=is_admin)
        if not success:
            return {"success": False, "error": "Username already exists"}
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/admin/api/users/{user_id}/detail")
async def admin_get_user_detail(user_id: int, session: Dict = Depends(require_admin)):
    """Get full user detail including all licenses and trial info."""
    try:
        user = get_full_user_detail(user_id)
        if not user:
            return {"error": "User not found"}
        return user
    except Exception as e:
        return {"error": str(e)}


@app.put("/admin/api/users/{user_id}")
async def admin_update_user(user_id: int, request: Request, session: Dict = Depends(require_admin)):
    """Update user details (admin only)."""
    try:
        body = await request.json()
        username = body.get("username")
        password = body.get("password")
        is_admin = body.get("is_admin")
        success = update_user_details(user_id, username=username, password=password, is_admin=is_admin)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.put("/admin/api/users/{user_id}/credits")
async def admin_update_credits(user_id: int, request: Request, session: Dict = Depends(require_admin)):
    """Update credits for a user (admin only)."""
    try:
        body = await request.json()
        credits = body.get("credits", 0)
        success = update_user_credits(user_id, credits)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/admin/api/users/{user_id}/licenses")
async def admin_add_license(user_id: int, request: Request, session: Dict = Depends(require_admin)):
    """Add a license key to a user (admin only)."""
    try:
        body = await request.json()
        license_key = body.get("license_key", "").strip()
        plan_id = body.get("plan_id", "pro")
        credits = body.get("credits", 300)
        expires_at = body.get("expires_at")
        if not license_key:
            return {"success": False, "error": "License key required"}
        success = db_add_user_license(user_id, license_key, plan_id=plan_id, credits=credits, expires_at=expires_at)
        if not success:
            return {"success": False, "error": "This license key is already active for this user."}
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/admin/api/licenses")
async def admin_get_all_licenses(session: Dict = Depends(require_admin)):
    """Get all licenses across all users."""
    try:
        users = get_all_users()
        all_licenses = []
        for u in users:
            user_lics = get_user_all_licenses(u["id"])
            for lic in user_lics:
                lic["user_id"] = u["id"]
                lic["username"] = u["username"]
                all_licenses.append(lic)
        return {"licenses": all_licenses}
    except Exception as e:
        return {"licenses": [], "error": str(e)}


@app.delete("/admin/api/licenses/{license_id}")
async def admin_revoke_license(license_id: int, session: Dict = Depends(require_admin)):
    """Revoke (delete) a single license record."""
    try:
        success = revoke_user_license(license_id)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/admin/api/stats")
async def admin_get_stats(session: Dict = Depends(require_admin)):
    """Get basic admin statistics."""
    try:
        users = get_all_users()
        total_users = len(users)
        total_gens = sum(u.get("generations_used", 0) for u in users)
        active_licenses = sum(1 for u in users if u.get("plan_id"))
        admin_users = sum(1 for u in users if u.get("is_admin"))
        return {
            "total_users": total_users,
            "total_generations": total_gens,
            "active_licenses": active_licenses,
            "admin_users": admin_users,
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/admin/api/users/{user_id}/reset-trial")
async def admin_reset_trial(user_id: int, session: Dict = Depends(require_admin)):
    """Reset trial for a user (admin only)."""
    try:
        success = reset_user_trial(user_id)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.delete("/admin/api/users/{user_id}")
async def admin_delete_user(user_id: int, session: Dict = Depends(require_admin)):
    """Delete a user (admin only)."""
    try:
        success = delete_user(user_id)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# Gumroad Webhook Endpoint
# ═══════════════════════════════════════════════════════════════

@app.post("/api/webhook/gumroad")
async def gumroad_webhook(request: Request):
    """
    Handle Gumroad webhook events (sale, refund, subscription_cancelled, etc.).

    Set this URL in Gumroad > Settings > Advanced > Ping endpoint:
    https://imageto3dpro.onrender.com/api/webhook/gumroad
    """
    try:
        from core.payment_factory import get_payment_processor

        # Gumroad sends form-encoded POST data
        payload = await request.form()
        payload_dict = dict(payload)

        print(f"[Webhook] Gumroad event received: {payload_dict.get('action', 'unknown')}")

        processor = get_payment_processor()

        # Verify webhook signature if configured
        signature = request.headers.get("X-Gumroad-Signature", "")
        if signature:
            is_valid = await processor.verify_webhook(str(payload_dict), signature)
            if not is_valid:
                print("[Webhook] Invalid signature — rejecting")
                return JSONResponse(
                    status_code=403,
                    content={"status": "error", "message": "Invalid signature"},
                )

        # Delegate to the provider's handle_webhook
        result = await processor.handle_webhook(payload_dict)

        print(f"[Webhook] Gumroad result: {result}")
        return {"status": "success", "result": result}

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Webhook] Error: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
