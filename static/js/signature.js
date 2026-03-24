/**
 * Signature Canvas functionality
 * Handles drawing, clearing, and capturing signatures
 */

const canvases = {};

function initSignatureCanvas(canvasType) {
    const canvas = document.getElementById(`${canvasType}-canvas`);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let isDrawing = false;
    let lastX = 0;
    let lastY = 0;

    // FIX: Set canvas internal dimensions to match display size
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;

    // Store canvas reference
    canvases[canvasType] = { canvas, ctx, isEmpty: true };

    // Set up drawing context
    ctx.strokeStyle = '#000';
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    // Mouse events
    canvas.addEventListener('mousedown', startDrawing);
    canvas.addEventListener('mousemove', draw);
    canvas.addEventListener('mouseup', stopDrawing);
    canvas.addEventListener('mouseout', stopDrawing);

    // Touch events for mobile with palm rejection
    canvas.addEventListener('touchstart', handleTouchStart, { passive: false });
    canvas.addEventListener('touchmove', handleTouchMove, { passive: false });
    canvas.addEventListener('touchend', handleTouchEnd, { passive: false });
    canvas.addEventListener('touchcancel', handleTouchEnd, { passive: false });

    function startDrawing(e) {
        isDrawing = true;
        [lastX, lastY] = getCoordinates(e);
        canvases[canvasType].isEmpty = false;
    }

    function draw(e) {
        if (!isDrawing) return;

        e.preventDefault();
        const [x, y] = getCoordinates(e);

        ctx.beginPath();
        ctx.moveTo(lastX, lastY);
        ctx.lineTo(x, y);
        ctx.stroke();

        [lastX, lastY] = [x, y];
    }

    function stopDrawing() {
        if (isDrawing) {
            isDrawing = false;
            // Save signature once after drawing stroke (not during every move)
            saveSignature(canvasType);
        }
    }

    function getCoordinates(e) {
        const rect = canvas.getBoundingClientRect();
        const clientX = e.clientX || (e.touches && e.touches[0].clientX);
        const clientY = e.clientY || (e.touches && e.touches[0].clientY);

        // Scale coordinates to match canvas internal resolution
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;

        const x = (clientX - rect.left) * scaleX;
        const y = (clientY - rect.top) * scaleY;

        return [x, y];
    }

    // Track the active drawing touch ID
    let activeTouchId = null;

    // Check if touch is likely from a stylus
    function isStylusTouch(touch) {
        // Modern browsers report touchType for stylus input
        if (touch.touchType === 'stylus') {
            return true;
        }
        
        // Fallback: Styluses typically have very small or zero radius
        const radiusX = touch.radiusX || 0;
        const radiusY = touch.radiusY || 0;
        return (radiusX <= 5 && radiusY <= 5);
    }

    // Check if touch is from palm (only when multiple touches exist)
    function isPalmTouch(touch, totalTouches) {
        // If only one touch, allow it (could be finger or stylus)
        if (totalTouches === 1) {
            return false;
        }
        
        // Multiple touches: filter large-radius touches (likely palm)
        const radiusX = touch.radiusX || 0;
        const radiusY = touch.radiusY || 0;
        const palmThreshold = 30; // Increased threshold for better iOS compatibility
        
        return (radiusX > palmThreshold || radiusY > palmThreshold);
    }

    function handleTouchStart(e) {
        // Prevent page scrolling/navigation
        e.preventDefault();
        
        // Find the best touch to use (prefer stylus, then first touch)
        let selectedTouch = null;
        
        for (let i = 0; i < e.touches.length; i++) {
            const touch = e.touches[i];
            
            // Skip palm touches when multiple touches exist
            if (isPalmTouch(touch, e.touches.length)) {
                continue;
            }
            
            // Prefer stylus touch
            if (isStylusTouch(touch)) {
                selectedTouch = touch;
                activeTouchId = touch.identifier;
                break;
            }
            
            // Otherwise use first non-palm touch
            if (!selectedTouch) {
                selectedTouch = touch;
                activeTouchId = touch.identifier;
            }
        }
        
        if (selectedTouch) {
            // Create synthetic event with the selected touch
            const syntheticEvent = {
                touches: [selectedTouch],
                preventDefault: () => {}
            };
            startDrawing(syntheticEvent);
        }
    }

    function handleTouchMove(e) {
        // Prevent page scrolling/navigation
        e.preventDefault();
        
        if (activeTouchId === null) return;
        
        // Find the active touch we're tracking
        let activeTouch = null;
        for (let i = 0; i < e.touches.length; i++) {
            if (e.touches[i].identifier === activeTouchId) {
                activeTouch = e.touches[i];
                break;
            }
        }
        
        if (activeTouch) {
            // Create synthetic event with the active touch
            const syntheticEvent = {
                touches: [activeTouch],
                preventDefault: () => {}
            };
            draw(syntheticEvent);
        }
    }

    function handleTouchEnd(e) {
        e.preventDefault();
        
        // Check if the active touch ended
        if (activeTouchId !== null) {
            let activeStillPresent = false;
            for (let i = 0; i < e.touches.length; i++) {
                if (e.touches[i].identifier === activeTouchId) {
                    activeStillPresent = true;
                    break;
                }
            }
            
            // If active touch is gone, stop drawing
            if (!activeStillPresent) {
                activeTouchId = null;
                stopDrawing();
            }
        }
    }
}

function clearCanvas(canvasType) {
    const canvasData = canvases[canvasType];
    if (!canvasData) return;

    const { canvas, ctx } = canvasData;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    canvasData.isEmpty = true;

    // Clear hidden input
    const input = document.getElementById(`${canvasType}_signature`);
    if (input) input.value = '';
}

function saveSignature(canvasType) {
    const canvasData = canvases[canvasType];
    if (!canvasData || canvasData.isEmpty) return;

    const { canvas } = canvasData;
    const dataURL = canvas.toDataURL('image/png');

    // Save to hidden input
    const input = document.getElementById(`${canvasType}_signature`);
    if (input) input.value = dataURL;
}

/**
 * Focus Mode - Fullscreen signature capture to avoid accidental Android navigation button touches
 */
let focusModeActive = false;
let focusModeCanvas = null;
let focusModeOverlay = null;
let focusCanvasInitialized = false;

function enterFocusMode(canvasType) {
    const originalCanvas = document.getElementById(`${canvasType}-canvas`);
    if (!originalCanvas) return;

    // Create fullscreen overlay if it doesn't exist
    if (!focusModeOverlay) {
        focusModeOverlay = document.createElement('div');
        focusModeOverlay.className = 'signature-fullscreen-overlay';
        focusModeOverlay.innerHTML = `
            <div class="signature-fullscreen-header">
                <h4 class="mb-0">Sign Here</h4>
                <div>
                    <button onclick="clearFocusModeCanvas()" class="btn btn-outline-secondary btn-sm me-2">
                        <i class="bi bi-arrow-counterclockwise"></i> Clear
                    </button>
                    <button onclick="exitFocusMode()" class="btn btn-primary btn-sm">
                        <i class="bi bi-check-lg"></i> Done
                    </button>
                </div>
            </div>
            <div class="signature-fullscreen-canvas-wrapper">
                <canvas id="focus-canvas" class="signature-fullscreen-canvas"></canvas>
                <p class="text-muted mt-3 small">
                    <i class="bi bi-info-circle"></i> Rest your hand freely - navigation buttons are hidden
                </p>
            </div>
        `;
        document.body.appendChild(focusModeOverlay);
    }

    // Store the canvas type we're working with
    focusModeOverlay.dataset.canvasType = canvasType;

    // Show overlay
    focusModeOverlay.classList.add('active');
    focusModeActive = true;

    // Get the focus canvas element
    focusModeCanvas = document.getElementById('focus-canvas');
    if (!focusModeCanvas) return;

    // Initialize signature canvas for focus mode (check if already in canvases map)
    if (!canvases['focus']) {
        initSignatureCanvas('focus');
    }
    
    // Set canvas dimensions
    const ctx = focusModeCanvas.getContext('2d');
    focusModeCanvas.width = focusModeCanvas.offsetWidth;
    focusModeCanvas.height = focusModeCanvas.offsetHeight;
    
    // ALWAYS reset the focus canvas to blank state first
    ctx.clearRect(0, 0, focusModeCanvas.width, focusModeCanvas.height);
    if (canvases['focus']) {
        canvases['focus'].isEmpty = true;
    }
    
    // Copy existing signature ONLY if source actually contains ink
    const sourceCanvasData = canvases[canvasType];
    const hasExistingSignature = sourceCanvasData && !sourceCanvasData.isEmpty;
    
    if (hasExistingSignature) {
        const existingData = originalCanvas.toDataURL();
        const img = new Image();
        img.onload = function() {
            ctx.drawImage(img, 0, 0, focusModeCanvas.width, focusModeCanvas.height);
            
            // Mark as not empty ONLY after confirming we copied actual content
            if (canvases['focus']) {
                canvases['focus'].isEmpty = false;
            }
        };
        img.src = existingData;
    }

    // Request fullscreen AFTER canvas is ready (must be synchronous within user gesture)
    requestFullscreen();
}

function exitFocusMode() {
    if (!focusModeActive) return;

    const canvasType = focusModeOverlay?.dataset.canvasType;
    
    // Copy signature back to original canvas only if focus canvas has content
    if (focusModeCanvas && canvasType) {
        const originalCanvas = document.getElementById(`${canvasType}-canvas`);
        const focusCanvasData = canvases['focus'];
        const hasFocusSignature = focusCanvasData && !focusCanvasData.isEmpty;
        
        if (originalCanvas && canvases[canvasType]) {
            if (hasFocusSignature) {
                // Copy signature back if there's actual content
                const focusData = focusModeCanvas.toDataURL();
                const img = new Image();
                img.onload = function() {
                    const ctx = originalCanvas.getContext('2d');
                    ctx.clearRect(0, 0, originalCanvas.width, originalCanvas.height);
                    ctx.drawImage(img, 0, 0, originalCanvas.width, originalCanvas.height);
                    
                    canvases[canvasType].isEmpty = false;
                    saveSignature(canvasType);
                };
                img.src = focusData;
            } else {
                // No signature in focus mode - clear original canvas and hidden input
                const ctx = originalCanvas.getContext('2d');
                ctx.clearRect(0, 0, originalCanvas.width, originalCanvas.height);
                canvases[canvasType].isEmpty = true;
                
                // Clear hidden input
                const input = document.getElementById(`${canvasType}_signature`);
                if (input) input.value = '';
            }
        }
    }

    // Hide overlay
    if (focusModeOverlay) {
        focusModeOverlay.classList.remove('active');
    }
    focusModeActive = false;

    // Exit fullscreen
    exitFullscreen();
}

function clearFocusModeCanvas() {
    if (focusModeCanvas) {
        const ctx = focusModeCanvas.getContext('2d');
        ctx.clearRect(0, 0, focusModeCanvas.width, focusModeCanvas.height);
        
        // Mark focus canvas as empty
        if (canvases['focus']) {
            canvases['focus'].isEmpty = true;
        }
        
        // Also clear the original canvas type's hidden input to prevent stale data
        const canvasType = focusModeOverlay?.dataset.canvasType;
        if (canvasType) {
            const input = document.getElementById(`${canvasType}_signature`);
            if (input) input.value = '';
        }
    }
}

function requestFullscreen() {
    const elem = document.documentElement;
    
    try {
        if (elem.requestFullscreen) {
            elem.requestFullscreen().catch(err => {
                console.warn('Fullscreen request failed:', err);
                showFullscreenWarning();
            });
        } else if (elem.webkitRequestFullscreen) {
            // Safari/iOS - returns void, not a promise
            elem.webkitRequestFullscreen();
        } else if (elem.mozRequestFullScreen) {
            // Firefox - returns void
            elem.mozRequestFullScreen();
        } else if (elem.msRequestFullscreen) {
            // IE/Edge - returns void
            elem.msRequestFullscreen();
        } else {
            showFullscreenWarning();
        }
    } catch (err) {
        console.warn('Fullscreen request failed:', err);
        showFullscreenWarning();
    }
    
    // Try to lock orientation to landscape for better signing experience
    try {
        if (screen.orientation && screen.orientation.lock) {
            screen.orientation.lock('landscape').catch(() => {
                // Orientation lock failed - that's okay
            });
        }
    } catch (err) {
        // Orientation lock not supported
    }
}

function showFullscreenWarning() {
    const wrapper = document.querySelector('.signature-fullscreen-canvas-wrapper');
    if (wrapper && !document.querySelector('.fullscreen-warning')) {
        const warning = document.createElement('div');
        warning.className = 'alert alert-warning small fullscreen-warning mt-2';
        warning.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Fullscreen mode unavailable. Try rotating your device to landscape for more space.';
        wrapper.appendChild(warning);
    }
}

function exitFullscreen() {
    if (document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
    } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
    } else if (document.mozCancelFullScreen) {
        document.mozCancelFullScreen();
    } else if (document.msExitFullscreen) {
        document.msExitFullscreen();
    }
    
    // Unlock orientation
    if (screen.orientation && screen.orientation.unlock) {
        screen.orientation.unlock();
    }
}
