from fastapi import FastAPI, UploadFile, Request, Form, HTTPException, Depends
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    FileResponse,
    RedirectResponse,
    Response,
)
import shutil
import os
import re
import platform
import psutil
import asyncio
import time
import uuid
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

app = FastAPI()

OUTPUT_DIR = Path("output").resolve()
SESSION_COOKIE = "imagetoad_session"
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
            .balance-box {
                margin-top: 8px;
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 12px;
                border-left: 3px solid rgba(148,163,184,0.6);
                background: rgba(30,41,59,0.6);
                color: #cbd5f5;
            }
            .balance-ok {
                border-left-color: #22c55e;
                background: rgba(21,128,61,0.15);
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
            .activity-log {
                margin-top: 10px;
                max-height: 200px;
                overflow-y: auto;
                scrollbar-width: thin;
                scrollbar-color: rgba(55,65,81,0.6) transparent;
            }
            .activity-log::-webkit-scrollbar {
                width: 5px;
            }
            .activity-log::-webkit-scrollbar-track {
                background: transparent;
            }
            .activity-log::-webkit-scrollbar-thumb {
                background: rgba(55,65,81,0.6);
                border-radius: 999px;
            }
            .activity-item {
                display: flex;
                align-items: flex-start;
                gap: 8px;
                padding: 6px 0;
                border-bottom: 1px solid rgba(55,65,81,0.3);
                font-size: 11px;
                color: #94a3b8;
                animation: fadeInSlide 0.3s ease-out;
            }
            .activity-item:last-child {
                border-bottom: none;
            }
            .activity-item.active {
                color: #e5e7eb;
            }
            .activity-item.active .activity-dot {
                background: #38bdf8;
                box-shadow: 0 0 6px rgba(56,189,248,0.6);
                animation: pulse-dot 1.5s ease-in-out infinite;
            }
            .activity-item.completed .activity-dot {
                background: #22c55e;
                box-shadow: 0 0 4px rgba(34,197,94,0.4);
            }
            .activity-dot {
                width: 6px;
                height: 6px;
                min-width: 6px;
                border-radius: 50%;
                background: #475569;
                margin-top: 4px;
                transition: all 0.3s ease;
            }
            .activity-ts {
                font-size: 10px;
                color: #64748b;
                min-width: 42px;
                font-variant-numeric: tabular-nums;
            }
            .activity-msg {
                flex: 1;
                line-height: 1.4;
            }
            .current-stage-label {
                font-size: 11px;
                color: #38bdf8;
                font-weight: 500;
                margin-top: 6px;
                display: flex;
                align-items: center;
                gap: 6px;
            }
            .current-stage-label .spinner {
                width: 12px;
                height: 12px;
                border: 2px solid rgba(56,189,248,0.25);
                border-top-color: #38bdf8;
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
            }
            @keyframes pulse-dot {
                0%, 100% { opacity: 1; transform: scale(1); }
                50% { opacity: 0.6; transform: scale(1.4); }
            }
            @keyframes fadeInSlide {
                from { opacity: 0; transform: translateY(-4px); }
                to { opacity: 1; transform: translateY(0); }
            }
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
            /* --- Warning & Error boxes --- */
            .warning-box {
                background: linear-gradient(135deg, rgba(251,191,36,0.15) 0%, rgba(245,158,11,0.10) 100%);
                border: 1px solid rgba(251,191,36,0.45);
                border-left: 4px solid #f59e0b;
                border-radius: 8px;
                padding: 12px 14px;
                margin: 10px 0;
                color: #fbbf24;
                font-size: 12px;
                line-height: 1.5;
                display: flex;
                gap: 10px;
                align-items: flex-start;
            }
            .warning-box::before {
                content: '\26A0';
                font-size: 18px;
                line-height: 1;
                flex-shrink: 0;
            }
            .warning-box strong {
                color: #fcd34d;
            }
            .error-box {
                background: linear-gradient(135deg, rgba(239,68,68,0.15) 0%, rgba(220,38,38,0.10) 100%);
                border: 1px solid rgba(239,68,68,0.45);
                border-left: 4px solid #ef4444;
                border-radius: 8px;
                padding: 12px 14px;
                margin: 10px 0;
                color: #fca5a5;
                font-size: 12px;
                line-height: 1.5;
                display: flex;
                gap: 10px;
                align-items: flex-start;
            }
            .error-box::before {
                content: '\2716';
                font-size: 18px;
                line-height: 1;
                flex-shrink: 0;
                color: #ef4444;
            }
            .error-box strong {
                color: #fecaca;
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
                    
                    <div class="option-group">
                        <label class="option-label">Balance</label>
                        <div class="balance-box" id="balanceInfo">Balance check not started.</div>
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
                    Local processing runs TripoSR on CPU and bakes a simple texture map from the input image (not full PBR materials). Keep at least 6GB RAM available for stable results.
                </div>
                <div class="progress-wrap" id="progressSection" style="display:none;">
                    <div style="font-size:12px; color:#e5e7eb;">Processing progress</div>
                    <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
                    <div class="progress-meta">
                        <div id="progressPercent">0%</div>
                        <div id="progressEta">ETA --:--</div>
                        <div id="progressElapsed">Elapsed 00:00</div>
                    </div>
                    <div class="current-stage-label" id="currentStageLabel" style="display:none;">
                        <div class="spinner"></div>
                        <span id="currentStageText">Initializing...</span>
                    </div>
                    <div class="activity-log" id="activityLog"></div>
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
            const balanceInfo = document.getElementById('balanceInfo');
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
            const currentStageLabel = document.getElementById('currentStageLabel');
            const currentStageText = document.getElementById('currentStageText');
            const activityLog = document.getElementById('activityLog');
            let serverHasCredentials = false;
            let lastTotalSeconds = null;
            let progressTimer = null;
            let progressStart = null;
            let progressExpected = null;
            let lastSystemInfo = null;
            let lastRenderedLogCount = 0;
            let backendPercent = null;  // set from poll data
            
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
            const creditCosts = {
                'hitem3dv1.5': { '512': 15, '1024': 20, '1536': 50, '1536pro': 70 },
                'hitem3dv2.0': { '1536': 75, '1536pro': 90 },
                'scene-portraitv1.5': { '1536': 70 },
                'scene-portraitv2.0': { '1536pro': 70 },
                'scene-portraitv2.1': { '1536pro': 70 }
            };
            let balanceState = { available: null, required: null, error: null, updatedAt: null };
            let balanceFetchTimer = null;

            function setStatus(text) {
                statusEl.textContent = text || '';
            }

            function updateApiTokenPlaceholder() {
                apiToken.placeholder = serverHasCredentials ? 'Using server credentials (optional)' : 'Enter your Hitem3D API token';
            }

            function formatCredits(value) {
                if (typeof value !== 'number' || Number.isNaN(value)) {
                    return '--';
                }
                return Number.isInteger(value) ? String(value) : value.toFixed(2);
            }

            function getRequiredCredits() {
                const modelCosts = creditCosts[apiModel.value];
                if (!modelCosts) return null;
                const value = modelCosts[apiResolution.value];
                return typeof value === 'number' ? value : null;
            }

            function setBalanceBox(message, stateClass) {
                balanceInfo.textContent = message || '';
                balanceInfo.classList.remove('balance-ok', 'balance-warn', 'balance-error');
                if (stateClass) {
                    balanceInfo.classList.add(stateClass);
                }
            }

            function updateBalanceInfo() {
                const useApi = document.querySelector('input[name="processing"]:checked').value === 'api';
                if (!useApi) {
                    setBalanceBox('Balance check is available for Hitem3D API.', '');
                    return;
                }
                const required = getRequiredCredits();
                balanceState.required = required;
                if (balanceState.error) {
                    setBalanceBox(balanceState.error, 'balance-error');
                    return;
                }
                if (balanceState.available === null || balanceState.available === undefined) {
                    if (required !== null) {
                        setBalanceBox(`Balance unavailable. Requires ${formatCredits(required)} credits.`, 'balance-warn');
                    } else {
                        setBalanceBox('Balance unavailable.', 'balance-warn');
                    }
                    return;
                }
                const availableText = formatCredits(balanceState.available);
                if (required === null) {
                    setBalanceBox(`Balance: ${availableText} credits.`, 'balance-ok');
                    return;
                }
                if (balanceState.available >= required) {
                    setBalanceBox(`Balance: ${availableText} credits (needs ${formatCredits(required)}).`, 'balance-ok');
                } else {
                    setBalanceBox(`Insufficient balance: ${availableText} credits (needs ${formatCredits(required)}).`, 'balance-error');
                }
            }

            function scheduleBalanceFetch() {
                if (balanceFetchTimer) {
                    clearTimeout(balanceFetchTimer);
                }
                balanceFetchTimer = setTimeout(fetchBalance, 600);
            }

            async function fetchBalance() {
                const useApi = document.querySelector('input[name="processing"]:checked').value === 'api';
                if (!useApi) return;
                const token = apiToken.value.trim();
                if (!serverHasCredentials && !token) {
                    balanceState.available = null;
                    balanceState.error = 'Add a valid API token to check balance.';
                    updateBalanceInfo();
                    return;
                }
                balanceState.error = null;
                setBalanceBox('Checking balance...', '');
                try {
                    const payload = new URLSearchParams();
                    if (token) {
                        payload.append('api_token', token);
                    }
                    const resp = await fetch('/hitem3d/balance', {
                        method: 'POST',
                        credentials: 'same-origin',
                        body: payload
                    });
                    if (!resp.ok) {
                        const error = await readResponseJson(resp);
                        const detail = error && (error.detail || error.error || error.error_message);
                        throw new Error(detail || `Server returned ${resp.status}`);
                    }
                    const data = await readResponseJson(resp) || {};
                    balanceState.available = typeof data.available === 'number' ? data.available : null;
                    balanceState.updatedAt = Date.now();
                } catch (err) {
                    const message = err && err.message ? err.message : 'Balance check failed.';
                    balanceState.available = null;
                    balanceState.error = `Balance check failed: ${message}`;
                }
                updateBalanceInfo();
            }

            function formatTime(totalSeconds) {
                const seconds = Math.max(0, Math.round(totalSeconds || 0));
                const minutes = Math.floor(seconds / 60);
                const rem = seconds % 60;
                return `${String(minutes).padStart(2, '0')}:${String(rem).padStart(2, '0')}`;
            }

            function updateProgress(elapsedSeconds) {
                const expected = progressExpected || 0;
                let percent;
                if (backendPercent !== null && backendPercent > 0) {
                    // Use real backend progress with slight smoothing
                    percent = backendPercent;
                } else {
                    // Fallback to time-estimation until backend reports
                    percent = expected > 0 ? (elapsedSeconds / expected) * 100 : 0;
                    percent = Math.max(0, Math.min(95, percent));
                }
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
                backendPercent = null;
                lastRenderedLogCount = 0;
                activityLog.innerHTML = '';
                currentStageLabel.style.display = 'flex';
                currentStageText.textContent = 'Uploading and starting...';
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
                    currentStageLabel.style.display = 'none';
                } else {
                    progressFill.style.width = '0%';
                    progressPercent.textContent = '0%';
                    progressEta.textContent = 'ETA --:--';
                    currentStageLabel.style.display = 'none';
                }
                backendPercent = null;
            }

            // --- Activity log & stage rendering helpers ---
            const stageIcons = {
                'starting': '🚀',
                'init': '⚙️',
                'load_and_infer': '🧠',
                'load_and_infer_done': '✅',
                'cleanup': '🧹',
                'advanced_processing': '🔧',
                'advanced_processing_done': '✅',
                'colorize': '🎨',
                'export': '📦',
                'done': '🎉'
            };

            function renderActivityLog(logEntries, currentStage) {
                if (!logEntries || logEntries.length === 0) return;
                // Only render new entries for efficiency
                const startIdx = lastRenderedLogCount;
                if (startIdx >= logEntries.length) {
                    // Just update active/completed states
                    const items = activityLog.querySelectorAll('.activity-item');
                    items.forEach(item => {
                        const stage = item.dataset.stage;
                        item.classList.remove('active');
                        if (stage === currentStage) {
                            item.classList.add('active');
                        } else {
                            item.classList.add('completed');
                        }
                    });
                    return;
                }
                // Mark existing items as completed
                const existingItems = activityLog.querySelectorAll('.activity-item');
                existingItems.forEach(item => {
                    item.classList.remove('active');
                    item.classList.add('completed');
                });
                // Add new entries
                for (let i = startIdx; i < logEntries.length; i++) {
                    const entry = logEntries[i];
                    const icon = stageIcons[entry.stage] || '📋';
                    const isLast = (i === logEntries.length - 1);
                    const elapsed = progressStart ? ((entry.ts * 1000 - progressStart) / 1000) : 0;
                    const tsStr = formatTime(Math.max(0, elapsed));
                    const div = document.createElement('div');
                    div.className = 'activity-item' + (isLast ? ' active' : ' completed');
                    div.dataset.stage = entry.stage;
                    div.innerHTML = `<div class="activity-dot"></div><span class="activity-ts">${tsStr}</span><span class="activity-msg">${icon} ${entry.msg}</span>`;
                    activityLog.appendChild(div);
                }
                lastRenderedLogCount = logEntries.length;
                // Auto-scroll to bottom
                activityLog.scrollTop = activityLog.scrollHeight;
            }

            function setResults(data) {
                resultsEl.innerHTML = '';
                if (!data) return;
                const { obj, stl, glb, fbx, usdz, obj_url, stl_url, glb_url, fbx_url, usdz_url, stats, processing_method, api_model, api_format, quality, warning, system_info, error_message } = data;
                const lines = [];
                
                if (error_message) {
                    lines.push(`<div class="error-box"><div><strong>Error:</strong> ${error_message}</div></div>`);
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
                    lines.push(`<div class="warning-box"><div><strong>Warning:</strong> ${warning}</div></div>`);
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
                    const req = system_info.ram_required_gb ?? 4;
                    // Color-code RAM: green (safe >=8), amber (warning 4-8), red (risky <4)
                    let ramColor = '#e5e7eb';
                    let ramLabel = '';
                    if (typeof free === 'number') {
                        if (free >= 8) { ramColor = '#4ade80'; ramLabel = ' (Excellent)'; }
                        else if (free >= 4) { ramColor = '#fbbf24'; ramLabel = ' (Moderate)'; }
                        else { ramColor = '#f87171'; ramLabel = ' (Low - may fail)'; }
                    }
                    lines.push(
                        `<div><strong>RAM:</strong> <span style="color:${ramColor};font-weight:600">${free}GB free${ramLabel}</span> / ${total}GB total (required ${req}GB)</div>`
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

            async function readResponseJson(resp) {
                const text = await resp.text();
                if (!text) return null;
                try {
                    return JSON.parse(text);
                } catch (e) {
                    return { error_message: text };
                }
            }

            function handleResult(data) {
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
            }

            function sleep(ms) {
                return new Promise(resolve => setTimeout(resolve, ms));
            }

            async function pollJob(jobId, useApi) {
                let attempts = 0;
                while (true) {
                    await sleep(2000);
                    attempts += 1;
                    const resp = await fetch(`/job/${jobId}`, {
                        credentials: 'same-origin'
                    });
                    if (!resp.ok) {
                        const error = await readResponseJson(resp);
                        const detail = error && (error.detail || error.error || error.error_message);
                        throw new Error(detail || `Server returned ${resp.status}`);
                    }
                    const data = await readResponseJson(resp) || {};
                    const status = data.status;

                    // Update backend progress in real-time
                    if (typeof data.progress_percent === 'number') {
                        backendPercent = data.progress_percent;
                    }
                    if (data.current_stage_msg) {
                        currentStageLabel.style.display = 'flex';
                        currentStageText.textContent = data.current_stage_msg;
                    }
                    if (data.progress_log) {
                        renderActivityLog(data.progress_log, data.current_stage);
                    }

                    if (status === 'queued') {
                        setStatus(useApi ? 'Queued for API processing...' : 'Queued for local processing...');
                    } else if (status === 'running') {
                        const stageMsg = data.current_stage_msg || (useApi ? 'Processing via Hitem3D API...' : 'Processing locally...');
                        setStatus(stageMsg);
                    } else if (status === 'done') {
                        handleResult(data.result || {});
                        return;
                    } else if (status === 'error') {
                        const msg = data.error_message || 'Processing failed';
                        setStatus(`Error: ${msg}`);
                        // Pass full result if available for system_info context
                        const resultData = data.result || { error_message: msg };
                        if (!resultData.error_message) resultData.error_message = msg;
                        setResults(resultData);
                        stopProgress(false);
                        return;
                    }
                    if (attempts > 1800) {
                        throw new Error('Processing timed out');
                    }
                }
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
                    : 'Local processing runs TripoSR on CPU and bakes a simple texture map from the input image (not full PBR materials). Keep at least 6GB RAM available for stable results.';
                updateModelInfo();
                updateBalanceInfo();
                if (useApi) {
                    scheduleBalanceFetch();
                }
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
                updateBalanceInfo();
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
                    scheduleBalanceFetch();
                } catch (e) {
                    setStatus(`Error: ${e.message}`);
                } finally {
                    saveServerToken.disabled = false;
                }
            });
            
            apiModel.addEventListener('change', updateModelInfo);
            apiResolution.addEventListener('change', updateBalanceInfo);
            apiToken.addEventListener('input', () => {
                balanceState.error = null;
                updateBalanceInfo();
                scheduleBalanceFetch();
            });

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
                    if (data.job_id) {
                        await pollJob(data.job_id, useApi);
                    } else {
                        handleResult(data);
                    }
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
                        if (info.available_gb !== null) {
                            sysAvailable.textContent = `${info.available_gb} GB`;
                            // Color-code: green (safe >=8), amber (warning 4-8), red (risky <4)
                            if (info.available_gb >= 8) {
                                sysAvailable.style.color = '#4ade80';
                            } else if (info.available_gb >= 4) {
                                sysAvailable.style.color = '#fbbf24';
                            } else {
                                sysAvailable.style.color = '#f87171';
                            }
                        } else {
                            sysAvailable.textContent = '--';
                            sysAvailable.style.color = '';
                        }
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
    if not is_password_configured():
        return RedirectResponse(url="/setup")
    if not verify_session_token(_get_session(request) or ""):
        return RedirectResponse(url="/login")
    return _main_app_html()


@app.get("/system-info")
async def system_info(_auth: bool = Depends(require_session)):
    try:
        mem = psutil.virtual_memory()
        required = 4.0
        return {
            "available_gb": round(mem.available / (1024**3), 2),
            "total_gb": round(mem.total / (1024**3), 2),
            "required_gb": required,
            "cpu_count": os.cpu_count(),
            "platform": platform.platform(),
        }
    except Exception:
        return {
            "available_gb": None,
            "total_gb": None,
            "required_gb": 4.0,
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

SETUP_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Set Password — Image to 3D</title>
    <style>
        body { font-family: system-ui, sans-serif; background: #1e293b; color: #e5e7eb; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .card { background: rgba(15,23,42,0.95); border-radius: 16px; padding: 28px; max-width: 380px; width: 100%; border: 1px solid rgba(148,163,184,0.25); }
        h1 { margin: 0 0 8px; font-size: 22px; }
        input { width: 100%; padding: 10px 12px; margin: 8px 0; border: 1px solid #475569; border-radius: 8px; background: #0f172a; color: #e5e7eb; box-sizing: border-box; }
        button { width: 100%; padding: 10px; margin-top: 12px; border: none; border-radius: 8px; background: #22c55e; color: white; font-weight: 600; cursor: pointer; }
        button:hover { filter: brightness(1.05); }
        .error { color: #f87171; font-size: 14px; margin-top: 8px; }
        .note { color: #94a3b8; font-size: 13px; margin: 0 0 8px; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Set Application Password</h1>
        <p class="note">Create a password before anyone can use the app.</p>
        <form method="post" action="/setup">
            <input type="password" name="password" placeholder="New password" required />
            <input type="password" name="confirm" placeholder="Confirm password" required />
            <button type="submit">Save password</button>
        </form>
        <p id="err" class="error"></p>
    </div>
    <script>
        const params = new URLSearchParams(location.search);
        const err = params.get('error');
        if (err === 'mismatch') document.getElementById('err').textContent = 'Passwords do not match.';
        if (err === 'short') document.getElementById('err').textContent = 'Password must be at least 8 characters.';
        if (err === 'failed') document.getElementById('err').textContent = 'Could not save password.';
        if (err === 'configured') document.getElementById('err').textContent = 'Password already set. Please log in.';
    </script>
</body>
</html>
"""

REGISTER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Register — Image to 3D</title>
    <style>
        body { font-family: system-ui, sans-serif; background: radial-gradient(circle at top, #1e293b, #020617); color: #e5e7eb; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .card { background: rgba(15,23,42,0.95); border-radius: 20px; padding: 32px; max-width: 400px; width: 100%; border: 1px solid rgba(148,163,184,0.25); }
        h1 { margin: 0 0 8px; font-size: 24px; color: #22c55e; }
        .subtitle { color: #94a3b8; margin: 0 0 20px; font-size: 14px; }
        input { width: 100%; padding: 12px 14px; margin: 8px 0; border: 1px solid #475569; border-radius: 10px; background: #0f172a; color: #e5e7eb; box-sizing: border-box; font-size: 14px; }
        input:focus { outline: none; border-color: #22c55e; box-shadow: 0 0 0 3px rgba(34,197,94,0.15); }
        button { width: 100%; padding: 14px; margin-top: 16px; border: none; border-radius: 10px; background: linear-gradient(135deg, #22c55e, #16a34a); color: white; font-weight: 600; font-size: 15px; cursor: pointer; transition: all 0.2s; }
        button:hover { filter: brightness(1.1); box-shadow: 0 8px 25px rgba(22,163,74,0.4); }
        .error { color: #f87171; font-size: 13px; margin-top: 10px; display: none; }
        .success { color: #22c55e; font-size: 13px; margin-top: 10px; display: none; }
        .login-link { text-align: center; margin-top: 20px; font-size: 14px; color: #94a3b8; }
        .login-link a { color: #22c55e; text-decoration: none; }
        .login-link a:hover { text-decoration: underline; }
        .trial-badge { display: inline-block; background: linear-gradient(135deg, #22c55e, #16a34a); padding: 6px 14px; border-radius: 999px; font-size: 12px; font-weight: 600; margin-bottom: 16px; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Create Account</h1>
        <p class="subtitle">Join ImageTo3D Pro today</p>
        
        <div class="trial-badge">1 FREE Generation</div>
        
        <form method="post" action="/register">
            <input type="text" name="username" placeholder="Username" required minlength="3" maxlength="30" pattern="[A-Za-z0-9_]+" title="Letters, numbers and underscores only" />
            <input type="email" name="email" placeholder="Email address" required />
            <input type="password" name="password" placeholder="Password" required minlength="6" />
            <input type="password" name="confirm" placeholder="Confirm password" required />
            <button type="submit">Create Account</button>
        </form>
        
        <p id="errorMsg" class="error"></p>
        <p id="successMsg" class="success"></p>
        
        <div class="login-link">
            Already have an account? <a href="/login">Log in</a>
        </div>
    </div>
    
    <script>
        const params = new URLSearchParams(location.search);
        const err = params.get('error');
        const errorMsg = document.getElementById('errorMsg');
        const successMsg = document.getElementById('successMsg');
        
        if (err === 'exists') {
            errorMsg.textContent = 'Username already taken. Please choose another.';
            errorMsg.style.display = 'block';
        } else if (err === 'mismatch') {
            errorMsg.textContent = 'Passwords do not match.';
            errorMsg.style.display = 'block';
        } else if (err === 'short') {
            errorMsg.textContent = 'Password must be at least 6 characters.';
            errorMsg.style.display = 'block';
        } else if (err === 'invalid') {
            errorMsg.textContent = 'Invalid username format. Use letters, numbers and underscores only.';
            errorMsg.style.display = 'block';
        } else if (params.get('registered') === '1') {
            successMsg.textContent = 'Account created! You can now log in.';
            successMsg.style.display = 'block';
        }
    </script>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Dashboard — Image to 3D</title>
    <style>
        body { font-family: system-ui, sans-serif; background: radial-gradient(circle at top, #1e293b, #020617); color: #e5e7eb; min-height: 100vh; margin: 0; }
        .container { max-width: 900px; margin: 0 auto; padding: 24px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid rgba(148,163,184,0.2); }
        .header h1 { margin: 0; font-size: 24px; color: #22c55e; }
        .header a { color: #94a3b8; text-decoration: none; font-size: 14px; }
        .header a:hover { color: #e5e7eb; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }
        .card { background: rgba(15,23,42,0.95); border-radius: 16px; padding: 24px; border: 1px solid rgba(148,163,184,0.25); }
        .card h2 { margin: 0 0 16px; font-size: 18px; color: #e5e7eb; }
        .stat { display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid rgba(55,65,81,0.5); }
        .stat:last-child { border-bottom: none; }
        .stat-label { color: #94a3b8; font-size: 14px; }
        .stat-value { font-weight: 600; font-size: 14px; }
        .stat-value.success { color: #22c55e; }
        .stat-value.warning { color: #f59e0b; }
        .stat-value.error { color: #ef4444; }
        .progress-bar { height: 8px; background: rgba(30,41,59,0.9); border-radius: 999px; margin: 12px 0; overflow: hidden; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #22c55e, #38bdf8); border-radius: 999px; transition: width 0.3s; }
        .btn { display: inline-block; width: 100%; padding: 12px; margin-top: 12px; border: none; border-radius: 10px; background: linear-gradient(135deg, #22c55e, #16a34a); color: white; font-weight: 600; font-size: 14px; cursor: pointer; text-align: center; text-decoration: none; box-sizing: border-box; }
        .btn:hover { filter: brightness(1.1); }
        .btn-secondary { background: rgba(55,65,81,0.8); }
        .btn-secondary:hover { background: rgba(75,85,101,0.8); }
        input { width: 100%; padding: 10px 12px; margin: 8px 0; border: 1px solid #475569; border-radius: 8px; background: #0f172a; color: #e5e7eb; box-sizing: border-box; font-size: 14px; }
        input:focus { outline: none; border-color: #22c55e; }
        .alert { padding: 12px; border-radius: 8px; margin-top: 12px; font-size: 13px; }
        .alert-success { background: rgba(21,128,61,0.2); border-left: 3px solid #22c55e; color: #a7f3d0; }
        .alert-error { background: rgba(127,29,29,0.2); border-left: 3px solid #ef4444; color: #fecdd3; }
        .user-info { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
        .avatar { width: 48px; height: 48px; border-radius: 50%; background: linear-gradient(135deg, #22c55e, #16a34a); display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: 600; }
        .user-details h2 { margin: 0 0 4px; font-size: 20px; }
        .user-details p { margin: 0; color: #94a3b8; font-size: 13px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Dashboard</h1>
            <div>
                <a href="/">Generate 3D</a> | 
                <a href="/logout">Logout</a>
            </div>
        </div>
        
        <div class="user-info">
            <div class="avatar">{{USERNAME_FIRST}}</div>
            <div class="user-details">
                <h2>{{USERNAME}}</h2>
                <p>Member since {{CREATED_AT}}</p>
            </div>
        </div>
        
        <div class="grid">
            <!-- Trial Status Card -->
            <div class="card">
                <h2>Trial Status</h2>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {{TRIAL_PERCENT}}%"></div>
                </div>
                <div class="stat">
                    <span class="stat-label">Generations Used</span>
                    <span class="stat-value">{{TRIAL_USED}}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Generations Remaining</span>
                    <span class="stat-value {{TRIAL_CLASS}}">{{TRIAL_REMAINING}}</span>
                </div>
                {{TRIAL_MESSAGE}}
            </div>
            
            <!-- License Status Card -->
            <div class="card">
                <h2>License Status</h2>
                <div class="stat">
                    <span class="stat-label">Plan</span>
                    <span class="stat-value">{{LICENSE_PLAN}}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Credits</span>
                    <span class="stat-value {{LICENSE_CLASS}}">{{LICENSE_CREDITS}}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Expires</span>
                    <span class="stat-value">{{LICENSE_EXPIRES}}</span>
                </div>
                {{LICENSE_MESSAGE}}
            </div>
            
            <!-- Quick Actions Card -->
            <div class="card">
                <h2>Quick Actions</h2>
                <a href="/" class="btn">Generate 3D Model</a>
                <a href="#" onclick="document.getElementById('licenseForm').style.display='block';return false;" class="btn btn-secondary">Activate License</a>
                <a href="#" onclick="document.getElementById('passwordForm').style.display='block';return false;" class="btn btn-secondary">Change Password</a>
            </div>
            
            <!-- Activate License Form -->
            <div class="card" id="licenseForm" style="display:none;">
                <h2>Activate License</h2>
                <form method="post" action="/dashboard/activate">
                    <input type="text" name="license_key" placeholder="Enter license key" required />
                    <button type="submit" class="btn">Activate</button>
                </form>
                <p id="licenseMsg"></p>
            </div>
            
            <!-- Change Password Form -->
            <div class="card" id="passwordForm" style="display:none;">
                <h2>Change Password</h2>
                <form method="post" action="/dashboard/password">
                    <input type="password" name="new_password" placeholder="New password" required minlength="6" />
                    <input type="password" name="confirm" placeholder="Confirm new password" required />
                    <button type="submit" class="btn">Update Password</button>
                </form>
                <p id="passwordMsg"></p>
            </div>
        </div>
    </div>
    
    <script>
        const params = new URLSearchParams(location.search);
        if (params.get('license') === 'success') {
            document.getElementById('licenseMsg').innerHTML = '<div class="alert alert-success">License activated successfully!</div>';
            document.getElementById('licenseForm').style.display = 'block';
        } else if (params.get('license') === 'error') {
            document.getElementById('licenseMsg').innerHTML = '<div class="alert alert-error">Invalid license key.</div>';
            document.getElementById('licenseForm').style.display = 'block';
        }
        if (params.get('password') === 'success') {
            document.getElementById('passwordMsg').innerHTML = '<div class="alert alert-success">Password updated successfully!</div>';
            document.getElementById('passwordForm').style.display = 'block';
        } else if (params.get('password') === 'error') {
            document.getElementById('passwordMsg').innerHTML = '<div class="alert alert-error">Passwords do not match.</div>';
            document.getElementById('passwordForm').style.display = 'block';
        }
    </script>
</body>
</html>
"""


@app.get("/setup", response_class=HTMLResponse)
async def setup_page():
    if is_password_configured():
        return RedirectResponse(url="/login")
    return SETUP_HTML


@app.post("/setup")
async def setup_post(password: str = Form(...), confirm: str = Form(...)):
    if is_password_configured():
        return RedirectResponse(url="/setup?error=configured", status_code=302)
    if password != confirm:
        return RedirectResponse(url="/setup?error=mismatch", status_code=302)
    if len(password) < 8:
        return RedirectResponse(url="/setup?error=short", status_code=302)
    try:
        set_password(password)
    except Exception:
        return RedirectResponse(url="/setup?error=failed", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Serve registration form."""
    # If already logged in, redirect to main app
    if verify_session_token(_get_session(request) or ""):
        return RedirectResponse(url="/")
    return REGISTER_HTML


@app.post("/register")
async def register_post(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
):
    """Register a new user."""
    # Validate username format
    if not re.match(r"^[A-Za-z0-9_]{3,30}$", username):
        return RedirectResponse(url="/register?error=invalid", status_code=302)

    # Validate password
    if len(password) < 6:
        return RedirectResponse(url="/register?error=short", status_code=302)

    # Check password match
    if password != confirm:
        return RedirectResponse(url="/register?error=mismatch", status_code=302)

    # Try to create user
    success = create_user(username, password, is_admin=False)

    if not success:
        return RedirectResponse(url="/register?error=exists", status_code=302)

    return RedirectResponse(url="/register?registered=1", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Serve user dashboard."""
    if not is_password_configured():
        return RedirectResponse(url="/setup")
    token = _get_session(request)
    if not verify_session_token(token or ""):
        return RedirectResponse(url="/login")

    # For now, just show a basic dashboard - user tracking will be added in Stage 5
    html = DASHBOARD_HTML
    html = html.replace("{{USERNAME}}", "User")
    html = html.replace("{{USERNAME_FIRST}}", "U")
    html = html.replace("{{CREATED_AT}}", "Today")
    html = html.replace("{{TRIAL_PERCENT}}", "100")
    html = html.replace("{{TRIAL_USED}}", "0")
    html = html.replace("{{TRIAL_REMAINING}}", "1")
    html = html.replace("{{TRIAL_CLASS}}", "success")
    html = html.replace(
        "{{TRIAL_MESSAGE}}", '<a href="/" class="btn">Generate 3D Model</a>'
    )
    html = html.replace("{{LICENSE_PLAN}}", "Trial")
    html = html.replace("{{LICENSE_CREDITS}}", "--")
    html = html.replace("{{LICENSE_CLASS}}", "")
    html = html.replace("{{LICENSE_EXPIRES}}", "Never")
    html = html.replace(
        "{{LICENSE_MESSAGE}}",
        '<a href="#" onclick="document.getElementById(\'licenseForm\').style.display=\'block\';return false;" class="btn btn-secondary">Purchase License</a>',
    )

    return html


@app.post("/dashboard/activate")
async def dashboard_activate_license(request: Request, license_key: str = Form(...)):
    """Activate a license key."""
    if not is_password_configured():
        return RedirectResponse(url="/setup")
    token = _get_session(request)
    if not verify_session_token(token or ""):
        return RedirectResponse(url="/login")

    # TODO: Validate license key and add to user
    # For now, just show error
    return RedirectResponse(url="/dashboard?license=error", status_code=302)


@app.post("/dashboard/password")
async def dashboard_change_password(
    request: Request, new_password: str = Form(...), confirm: str = Form(...)
):
    """Change user password."""
    if not is_password_configured():
        return RedirectResponse(url="/setup")
    token = _get_session(request)
    if not verify_session_token(token or ""):
        return RedirectResponse(url="/login")

    if new_password != confirm:
        return RedirectResponse(url="/dashboard?password=error", status_code=302)

    # TODO: Update password for logged-in user
    return RedirectResponse(url="/dashboard?password=success", status_code=302)


# Admin HTML Template
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Admin Panel — Image to 3D</title>
    <style>
        body { font-family: system-ui, sans-serif; background: radial-gradient(circle at top, #1e293b, #020617); color: #e5e7eb; min-height: 100vh; margin: 0; }
        .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid rgba(148,163,184,0.2); }
        .header h1 { margin: 0; font-size: 24px; color: #22c55e; }
        .header a { color: #94a3b8; text-decoration: none; font-size: 14px; }
        .card { background: rgba(15,23,42,0.95); border-radius: 16px; padding: 24px; border: 1px solid rgba(148,163,184,0.25); margin-bottom: 20px; }
        .card h2 { margin: 0 0 16px; font-size: 18px; color: #e5e7eb; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid rgba(55,65,81,0.5); font-size: 14px; }
        th { color: #94a3b8; font-weight: 500; text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em; }
        tr:hover { background: rgba(30,41,59,0.5); }
        .badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 600; }
        .badge-admin { background: rgba(239,68,68,0.2); color: #f87171; }
        .badge-user { background: rgba(34,197,94,0.2); color: #22c55e; }
        .badge-trial { background: rgba(251,191,36,0.2); color: #fbbf24; }
        .badge-license { background: rgba(59,130,246,0.2); color: #60a5fa; }
        .btn { display: inline-block; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 500; cursor: pointer; border: none; text-decoration: none; }
        .btn-danger { background: rgba(239,68,68,0.2); color: #f87171; }
        .btn-danger:hover { background: rgba(239,68,68,0.3); }
        .btn-warning { background: rgba(251,191,36,0.2); color: #fbbf24; }
        .btn-warning:hover { background: rgba(251,191,36,0.3); }
        .btn-primary { background: rgba(34,197,94,0.2); color: #22c55e; }
        .btn-primary:hover { background: rgba(34,197,94,0.3); }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
        .stat-box { background: rgba(15,23,42,0.8); border: 1px solid rgba(55,65,81,0.5); border-radius: 12px; padding: 16px; }
        .stat-box .value { font-size: 28px; font-weight: 700; color: #22c55e; }
        .stat-box .label { font-size: 12px; color: #94a3b8; margin-top: 4px; }
        .form-inline { display: flex; gap: 12px; align-items: flex-end; }
        .form-inline input { flex: 1; margin: 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Admin Panel</h1>
            <div><a href="/logout">Logout</a></div>
        </div>
        <div class="stats-grid">
            <div class="stat-box"><div class="value">{{TOTAL_USERS}}</div><div class="label">Total Users</div></div>
            <div class="stat-box"><div class="value">{{TOTAL_ADMINS}}</div><div class="label">Admins</div></div>
            <div class="stat-box"><div class="value">{{TRIAL_USERS}}</div><div class="label">On Trial</div></div>
            <div class="stat-box"><div class="value">{{LICENSE_USERS}}</div><div class="label">With License</div></div>
        </div>
        <div class="card">
            <h2>Add New User</h2>
            <form method="post" action="/admin/add-user" class="form-inline">
                <input type="text" name="username" placeholder="Username" required />
                <input type="password" name="password" placeholder="Password" required />
                <button type="submit" class="btn btn-primary">Add User</button>
            </form>
        </div>
        <div class="card">
            <h2>All Users</h2>
            <table><thead><tr><th>ID</th><th>Username</th><th>Created</th><th>Role</th><th>Trial</th><th>License</th><th>Actions</th></tr></thead>
            <tbody>{{USER_ROWS}}</tbody></table>
        </div>
    </div>
</body>
</html>
"""

ADMIN_LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Admin Login — Image to 3D</title>
    <style>
        body { font-family: system-ui, sans-serif; background: radial-gradient(circle at top, #1e293b, #020617); color: #e5e7eb; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .card { background: rgba(15,23,42,0.95); border-radius: 20px; padding: 32px; max-width: 400px; width: 100%; border: 1px solid rgba(148,163,184,0.25); }
        h1 { margin: 0 0 8px; font-size: 24px; color: #ef4444; }
        .subtitle { color: #94a3b8; margin: 0 0 20px; font-size: 14px; }
        input { width: 100%; padding: 12px 14px; margin: 8px 0; border: 1px solid #475569; border-radius: 10px; background: #0f172a; color: #e5e7eb; box-sizing: border-box; font-size: 14px; }
        button { width: 100%; padding: 14px; margin-top: 16px; border: none; border-radius: 10px; background: linear-gradient(135deg, #ef4444, #dc2626); color: white; font-weight: 600; font-size: 15px; cursor: pointer; }
        .error { color: #f87171; font-size: 13px; margin-top: 10px; display: none; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Admin Login</h1>
        <p class="subtitle">Restricted access</p>
        <form method="post" action="/admin/login">
            <input type="text" name="username" placeholder="Admin username" required autofocus />
            <input type="password" name="password" placeholder="Password" required />
            <button type="submit">Login</button>
        </form>
        <p id="errorMsg" class="error"></p>
    </div>
    <script>
        const params = new URLSearchParams(location.search);
        if (params.get('error') === '1') {
            document.getElementById('errorMsg').textContent = 'Invalid admin credentials.';
            document.getElementById('errorMsg').style.display = 'block';
        }
    </script>
</body>
</html>
"""


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    if not is_password_configured():
        return RedirectResponse(url="/setup")
    return ADMIN_LOGIN_HTML


@app.post("/admin/login")
async def admin_login_post(username: str = Form(...), password: str = Form(...)):
    if not is_password_configured():
        return RedirectResponse(url="/setup")
    user_id = verify_user(username, password)
    if not user_id or not is_user_admin(user_id):
        return RedirectResponse(url="/admin/login?error=1", status_code=302)
    token = create_session_token()
    response = RedirectResponse(url="/admin/users", status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        max_age=SESSION_MAX_AGE,
        samesite="lax",
    )
    return response


@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    if not is_password_configured():
        return RedirectResponse(url="/setup")
    token = _get_session(request)
    if not verify_session_token(token or ""):
        return RedirectResponse(url="/admin/login")
    users = get_all_users()
    total_users = len(users)
    total_admins = sum(1 for u in users if u.get("is_admin"))
    trial_users = sum(
        1
        for u in users
        if u.get("generations_remaining", 0) > 0 and not u.get("plan_id")
    )
    license_users = sum(1 for u in users if u.get("plan_id"))
    user_rows = []
    for u in users:
        role_badge = (
            '<span class="badge badge-admin">Admin</span>'
            if u.get("is_admin")
            else '<span class="badge badge-user">User</span>'
        )
        trial = f"{u.get('generations_remaining', 0)} left"
        license_badge = u.get("plan_id") or "-"
        actions = ""
        if not u.get("is_admin"):
            actions = f'''<form method="post" action="/admin/reset-trial" style="display:inline"><input type="hidden" name="user_id" value="{u["id"]}"><button type="submit" class="btn btn-warning">Reset</button></form>'''
        user_rows.append(
            f"<tr><td>{u['id']}</td><td>{u['username']}</td><td>{u.get('created_at', '')[:10]}</td><td>{role_badge}</td><td>{trial}</td><td>{license_badge}</td><td>{actions}</td></tr>"
        )
    html = (
        ADMIN_HTML.replace("{{TOTAL_USERS}}", str(total_users))
        .replace("{{TOTAL_ADMINS}}", str(total_admins))
        .replace("{{TRIAL_USERS}}", str(trial_users))
        .replace("{{LICENSE_USERS}}", str(license_users))
        .replace("{{USER_ROWS}}", "\n".join(user_rows))
    )
    return html


@app.post("/admin/add-user")
async def admin_add_user(
    request: Request, username: str = Form(...), password: str = Form(...)
):
    if not is_password_configured():
        return RedirectResponse(url="/setup")
    token = _get_session(request)
    if not verify_session_token(token or ""):
        return RedirectResponse(url="/admin/login")
    create_user(username, password, is_admin=False)
    return RedirectResponse(url="/admin/users?success=added", status_code=302)


@app.post("/admin/reset-trial")
async def admin_reset_trial(request: Request, user_id: int = Form(...)):
    if not is_password_configured():
        return RedirectResponse(url="/setup")
    token = _get_session(request)
    if not verify_session_token(token or ""):
        return RedirectResponse(url="/admin/login")
    reset_user_trial(user_id)
    return RedirectResponse(url="/admin/users?success=reset", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Serve login form."""
    if not is_password_configured():
        return RedirectResponse(url="/setup")
    return LOGIN_HTML


@app.post("/login")
async def login_post(password: str = Form(...)):
    """Verify password (server-side bcrypt) and set session cookie."""
    if not is_password_configured():
        return RedirectResponse(url="/setup")
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


async def _run_job(
    job_id: str,
    input_path: str,
    safe_name: str,
    use_api: bool,
    api_token: Optional[str],
    api_model: Optional[str],
    api_resolution: Optional[str],
    api_format: Optional[str],
    quality: str,
):
    JOBS[job_id]["status"] = "running"
    JOBS[job_id]["updated_at"] = time.time()
    JOBS[job_id]["progress_percent"] = 0
    JOBS[job_id]["current_stage"] = "starting"
    JOBS[job_id]["current_stage_msg"] = "Starting processing..."
    JOBS[job_id]["progress_log"] = []

    def _progress_cb(stage: str, pct: int, msg: str):
        """Called from the pipeline thread to update real-time progress."""
        JOBS[job_id]["current_stage"] = stage
        JOBS[job_id]["current_stage_msg"] = msg
        JOBS[job_id]["progress_percent"] = max(0, min(100, pct))
        JOBS[job_id]["updated_at"] = time.time()
        JOBS[job_id].setdefault("progress_log", []).append(
            {"stage": stage, "pct": pct, "msg": msg, "ts": time.time()}
        )

    try:
        result = await run_pipeline_async(
            input_path,
            name=safe_name,
            use_api=use_api,
            api_token=api_token,
            api_model=api_model,
            api_resolution=api_resolution,
            api_format=api_format,
            quality=quality
            if quality in ("draft", "standard", "high", "production")
            else "standard",
            progress_callback=_progress_cb,
        )
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

        # Check if the pipeline returned an error dict (TripoSR failure
        # caught internally by unified_pipeline)
        if result.get("error_message"):
            JOBS[job_id].update(
                {
                    "status": "error",
                    "result": result,
                    "error_message": result["error_message"],
                    "updated_at": time.time(),
                    "progress_percent": 0,
                    "current_stage": "error",
                    "current_stage_msg": result["error_message"][:150],
                }
            )
        else:
            JOBS[job_id].update(
                {
                    "status": "done",
                    "result": result,
                    "updated_at": time.time(),
                    "progress_percent": 100,
                    "current_stage": "done",
                    "current_stage_msg": "Processing complete!",
                }
            )
    except InsufficientBalanceError as e:
        JOBS[job_id].update(
            {"status": "error", "error_message": str(e), "updated_at": time.time()}
        )
    except Exception as e:
        JOBS[job_id].update(
            {"status": "error", "error_message": str(e), "updated_at": time.time()}
        )


@app.get("/job/{job_id}")
async def job_status(job_id: str, _auth: bool = Depends(require_session)):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _prune_jobs()
    payload = {"job_id": job_id, "status": job.get("status")}
    if job.get("error_message"):
        payload["error_message"] = job["error_message"]
    if job.get("result"):
        payload["result"] = job["result"]
    # Real-time progress info
    if job.get("progress_percent") is not None:
        payload["progress_percent"] = job["progress_percent"]
    if job.get("current_stage"):
        payload["current_stage"] = job["current_stage"]
    if job.get("current_stage_msg"):
        payload["current_stage_msg"] = job["current_stage_msg"]
    if job.get("progress_log"):
        payload["progress_log"] = job["progress_log"]
    return payload


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
        if not (
            credentials["access_token"]
            or (credentials["client_id"] and credentials["client_secret"])
        ):
            raise HTTPException(
                status_code=400,
                detail="Hitem3D credentials are required when using Hitem3D API",
            )
        # Only validate token when user provided one (skip when using server-side credentials)
        if api_token and api_token.strip():
            if not await validate_api_token(api_token.strip()):
                raise HTTPException(
                    status_code=400, detail="Invalid Hitem3D API credentials"
                )
    else:
        # Local processing with TripoSR - takes 5-15 minutes on CPU
        try:
            available_gb = psutil.virtual_memory().available / (1024**3)
            if available_gb < 2.5:
                raise HTTPException(
                    status_code=400,
                    detail="Local processing requires at least 2.5GB available RAM. Please close other applications or use Hitem3D API.",
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

    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "status": "queued",
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    _prune_jobs()
    asyncio.create_task(
        _run_job(
            job_id,
            input_path,
            safe_name,
            use_api,
            api_token,
            api_model,
            api_resolution,
            api_format,
            quality,
        )
    )
    return {"job_id": job_id, "status": "queued"}


@app.post("/credentials/update")
async def update_credentials(
    token: str = Form(...), _auth: bool = Depends(require_session)
):
    raw = (token or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="API token is required")
    if not await validate_api_token(raw):
        raise HTTPException(status_code=400, detail="Invalid Hitem3D API credentials")
    save_hitem3d_credentials(raw)
    return {"saved": True}


@app.post("/hitem3d/balance")
async def hitem3d_balance(
    api_token: Optional[str] = Form(None), _auth: bool = Depends(require_session)
):
    result = await get_hitem3d_balance(api_token.strip() if api_token else None)
    if result.get("error") == "credentials_missing":
        raise HTTPException(
            status_code=400, detail="Hitem3D credentials are required to check balance"
        )
    return {"available": result.get("available")}


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
async def credentials_availability(
    request: Request, _auth: bool = Depends(require_session)
):
    """Check if server-side Hitem3D credentials are available."""
    creds = resolve_hitem3d_credentials(None)
    available = bool(
        creds["access_token"] or (creds["client_id"] and creds["client_secret"])
    )
    return {"available": available}
