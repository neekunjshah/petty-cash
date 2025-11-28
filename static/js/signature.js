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

    // Touch events for mobile
    canvas.addEventListener('touchstart', handleTouchStart);
    canvas.addEventListener('touchmove', handleTouchMove);
    canvas.addEventListener('touchend', stopDrawing);

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

        // Save signature as base64
        saveSignature(canvasType);
    }

    function stopDrawing() {
        isDrawing = false;
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

    function handleTouchStart(e) {
        e.preventDefault();
        startDrawing(e);
    }

    function handleTouchMove(e) {
        e.preventDefault();
        draw(e);
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
