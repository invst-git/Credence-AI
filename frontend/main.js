/**
 * Credence - Tata Capital Personal Loan Assistant
 * Multi-Agent Frontend with Document Capture Support
 */

// ========== DOM Elements ==========
const chatEl = document.getElementById("chat");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
// Camera button removed from footer
const newChatBtn = document.getElementById("newChatBtn");
const applyBtn = document.getElementById("applyBtn");
const agentStatusEl = document.getElementById("agentStatus");

// Capture Modal Elements
const captureModal = document.getElementById("captureModal");
const captureTitle = document.getElementById("captureTitle");
const closeCaptureBtn = document.getElementById("closeCaptureBtn");
const cameraPreview = document.getElementById("cameraPreview");
const captureCanvas = document.getElementById("captureCanvas");
const capturedImage = document.getElementById("capturedImage");
const captureBtn = document.getElementById("captureBtn");
const retakeBtn = document.getElementById("retakeBtn");
const confirmCaptureBtn = document.getElementById("confirmCaptureBtn");
const captureTips = document.getElementById("captureTips");

// OTP Notification Elements
const otpNotification = document.getElementById("otpNotification");
const otpNotificationCode = document.getElementById("otpNotificationCode");

// ========== Configuration ==========
const API_BASE = window.CONFIG?.API_BASE_URL || "http://127.0.0.1:8000";
const API_URL = `${API_BASE}/eligibility/chat`;
const UPLOAD_API_URL = `${API_BASE}/eligibility/upload-document`;
const LOAN_DECISION_API_URL = `${API_BASE}/eligibility/loan-decision`;

// ========== State ==========
let threadId = localStorage.getItem("credence_thread_id");
let currentCaptureMode = null; // "selfie" | "aadhaar_front" | "aadhaar_back"
let mediaStream = null;
let lastCapturedImage = null; // Store the last captured image base64
let isOTPMode = false; // Track if we're in OTP input mode

// Document Upload State
let customerUUID = null;
let uploadedDocuments = {};
let requiredDocuments = [];

// Initialize thread ID
function initThread() {
  threadId = "thread_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  localStorage.setItem("credence_thread_id", threadId);
}

if (!threadId) {
  initThread();
}

// ========== Agent Status Mapping ==========
const agentLabels = {
  master: "Master Agent",
  sales: "Sales Agent",
  eligibility: "Eligibility Agent",
  document_verification: "Document Verification",
};

function updateAgentStatus(agent) {
  if (agentStatusEl && agentLabels[agent]) {
    agentStatusEl.textContent = agentLabels[agent];
  }
}

// ========== Message Rendering ==========

// Parse markdown tables into HTML tables
function parseMarkdownTable(text) {
  const lines = text.split('\n');
  let result = [];
  let inTable = false;
  let tableHtml = '';
  let isFirstDataRow = true;

  for (const line of lines) {
    const trimmed = line.trim();

    // Check if this is a table row (starts and ends with |)
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      // Skip separator row (|---|---|)
      if (trimmed.includes('---')) continue;

      if (!inTable) {
        inTable = true;
        tableHtml = '<table class="info-table">';
        isFirstDataRow = true;
      }

      const cells = trimmed.split('|').filter(c => c.trim());
      const cellTag = isFirstDataRow ? 'th' : 'td';
      tableHtml += '<tr>' + cells.map(c => `<${cellTag}>${c.trim()}</${cellTag}>`).join('') + '</tr>';
      isFirstDataRow = false;
    } else {
      if (inTable) {
        tableHtml += '</table>';
        result.push(tableHtml);
        inTable = false;
        tableHtml = '';
      }
      result.push(line);
    }
  }

  if (inTable) {
    tableHtml += '</table>';
    result.push(tableHtml);
  }

  return result.join('\n');
}

function appendMessage(role, text) {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  // First parse markdown tables
  let formattedText = parseMarkdownTable(text);

  // Then parse other markdown-style formatting
  formattedText = formattedText
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/_(.+?)_/g, '<em>$1</em>');

  // Detect verification status lines (ending with "...") and apply shimmer
  formattedText = formattedText.split('\n').map(line => {
    const trimmed = line.trim();
    // Check if line looks like a status message
    if (trimmed.endsWith('...') &&
      (trimmed.includes('Verifying') ||
        trimmed.includes('Analyzing') ||
        trimmed.includes('Processing') ||
        trimmed.includes('Checking') ||
        trimmed.includes('underwriting') ||
        trimmed.includes('assessment'))) {
      return `<div class="verification-status"><div class="status-icon"></div><span class="shimmer-text">${trimmed}</span></div>`;
    }
    return line;
  }).join('\n');

  formattedText = formattedText.replace(/\n/g, '<br>');

  bubble.innerHTML = formattedText;

  row.appendChild(bubble);
  chatEl.appendChild(row);
  chatEl.scrollTop = chatEl.scrollHeight;

  return bubble;
}

function appendTypingIndicator(message = "Thinking...") {
  const row = document.createElement("div");
  row.className = "message-row assistant";
  row.id = "typingIndicator";

  const bubble = document.createElement("div");
  bubble.className = "bubble typing-indicator";
  bubble.innerHTML = `<span class="shimmer-text">${message}</span>`;

  row.appendChild(bubble);
  chatEl.appendChild(row);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function removeTypingIndicator() {
  const indicator = document.getElementById("typingIndicator");
  if (indicator) {
    indicator.remove();
  }
}

// ========== API Communication ==========
async function sendMessage(imageData = null, imageType = null) {
  const text = inputEl.value.trim();
  if (!text) return;

  appendMessage("user", text);
  inputEl.value = "";
  inputEl.focus();

  // Show contextual loading message based on what's being sent
  let loadingMessage = "Thinking...";
  if (imageType === "selfie") {
    loadingMessage = "Analyzing selfie...";
  } else if (imageType === "aadhaar_front") {
    loadingMessage = "Extracting Aadhaar details...";
  } else if (imageType === "aadhaar_back") {
    loadingMessage = "Processing Aadhaar back...";
  } else if (text.toLowerCase() === "captured") {
    loadingMessage = "Analyzing image...";
  }

  appendTypingIndicator(loadingMessage);

  try {
    const payload = {
      thread_id: threadId,
      user_message: text,
    };

    // Add image data if provided
    if (imageData) {
      payload.image_data = imageData;
      payload.image_type = imageType;
    }

    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    removeTypingIndicator();

    if (!res.ok) {
      appendMessage(
        "assistant",
        "Something went wrong on the server. Please try again."
      );
      return;
    }

    const data = await res.json();
    const assistantMessage = data.assistant_message || "(no reply)";

    const bubble = appendMessage("assistant", assistantMessage);

    // Update agent status if provided
    if (data.current_agent) {
      updateAgentStatus(data.current_agent);
    }

    // Check for OTP notification
    if (data.otp_notification) {
      showOTPNotification(data.otp_notification);
    }

    // Check if OTP input is needed (only if not already in OTP mode)
    if (data.doc_verification_stage === "awaiting_otp" && !isOTPMode) {
      renderOTPInput(bubble);
    } else if (data.doc_verification_stage === "document_upload") {
      // Store customer UUID for document uploads
      if (data.customer_uuid) {
        customerUUID = data.customer_uuid;
      }
      // Render document upload UI
      if (data.required_documents && data.required_documents.length > 0) {
        renderDocumentUploadUI(bubble, data.required_documents, data.uploaded_documents);
      }
    } else if (data.doc_verification_stage === "pan_retry") {
      // Store customer UUID if provided
      if (data.customer_uuid) {
        customerUUID = data.customer_uuid;
      }
      // Render single PAN upload box for retry
      renderPANRetryUI(bubble);
    } else if (data.doc_verification_stage === "employment_retry") {
      if (data.customer_uuid) customerUUID = data.customer_uuid;
      renderDocRetryUI(bubble, "employment_certificate", "Employment Certificate");
    } else if (data.doc_verification_stage === "salary_retry") {
      if (data.customer_uuid) customerUUID = data.customer_uuid;
      renderDocRetryUI(bubble, "salary_slips", "Salary Slips");
    } else if (data.doc_verification_stage === "bank_retry") {
      if (data.customer_uuid) customerUUID = data.customer_uuid;
      renderDocRetryUI(bubble, "bank_statements", "Bank Statements");
    } else if (data.doc_verification_stage === "address_retry") {
      if (data.customer_uuid) customerUUID = data.customer_uuid;
      renderDocRetryUI(bubble, "address_proof", "Address Proof");
    } else if (data.doc_verification_stage === "loan_approved" && data.underwriting_result) {
      // Render loan approval UI instead of text
      renderLoanApprovalUI(bubble, data.underwriting_result);
    } else if (data.doc_verification_stage !== "awaiting_otp") {
      // Check if document capture is needed
      checkForCaptureMode(assistantMessage, bubble, data);
    }

  } catch (err) {
    removeTypingIndicator();
    appendMessage(
      "assistant",
      "Unable to reach the server. Is the backend running on 127.0.0.1:8000?"
    );
  }
}

// ========== Document Capture Detection ==========
function checkForCaptureMode(message, bubbleEl, data = {}) {
  const lowerMessage = message.toLowerCase();
  let mode = null;
  let label = "";

  if (lowerMessage.includes("live selfie") || lowerMessage.includes("step 1 of 3")) {
    mode = "selfie";
    label = "Capture Selfie";
    captureTips.textContent = "Position your face in the center and look at the camera";
  } else if (lowerMessage.includes("aadhaar card (front)") || lowerMessage.includes("step 2 of 3")) {
    mode = "aadhaar_front";
    label = "Capture Aadhaar Front";
    captureTips.textContent = "Place Aadhaar card on a flat surface with good lighting";
  } else if (lowerMessage.includes("aadhaar card (back)") || lowerMessage.includes("step 3 of 3")) {
    mode = "aadhaar_back";
    label = "Capture Aadhaar Back";
    captureTips.textContent = "Flip the card and capture the back with address visible";
  }

  if (mode) {
    currentCaptureMode = mode;
    isOTPMode = false;

    // Disable input
    inputEl.disabled = true;
    inputEl.placeholder = "Please complete document capture...";
    sendBtn.disabled = true;

    // Add inline button
    const btn = document.createElement("button");
    btn.className = "inline-action-btn";
    btn.innerHTML = label;
    btn.onclick = openCamera;

    // Append break and button
    bubbleEl.appendChild(document.createElement("br"));
    bubbleEl.appendChild(btn);
  } else if (lowerMessage.includes("identity has been verified") ||
    lowerMessage.includes("document upload") ||
    lowerMessage.includes("verification complete")) {
    currentCaptureMode = null;
    isOTPMode = false;
    // Ensure input is enabled
    inputEl.disabled = false;
    inputEl.placeholder = "Type your message...";
    sendBtn.disabled = false;
  }
}

// ========== Camera Functions ==========
async function openCamera() {
  if (!currentCaptureMode) return;

  // Set modal title based on mode
  const titles = {
    selfie: "Capture Live Selfie",
    aadhaar_front: "Capture Aadhaar Front",
    aadhaar_back: "Capture Aadhaar Back",
  };
  captureTitle.textContent = titles[currentCaptureMode] || "Capture Document";

  // Show modal
  captureModal.classList.remove("hidden");

  // Reset UI
  capturedImage.classList.add("hidden");
  cameraPreview.classList.remove("hidden");
  captureBtn.classList.remove("hidden");
  retakeBtn.classList.add("hidden");
  confirmCaptureBtn.classList.add("hidden");

  try {
    // Request camera access
    const constraints = {
      video: {
        facingMode: currentCaptureMode === "selfie" ? "user" : "environment",
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
    };

    mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
    cameraPreview.srcObject = mediaStream;
  } catch (err) {
    console.error("Camera access error:", err);
    alert("Unable to access camera. Please grant camera permission and try again.");
    closeCamera();
  }
}

function capturePhoto() {
  const canvas = captureCanvas;
  const video = cameraPreview;

  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;

  const ctx = canvas.getContext("2d");

  // For selfie, flip horizontally for mirror effect
  if (currentCaptureMode === "selfie") {
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
  }

  ctx.drawImage(video, 0, 0);

  // Convert to image and store for upload
  const imageDataUrl = canvas.toDataURL("image/jpeg", 0.85);
  capturedImage.src = imageDataUrl;
  lastCapturedImage = imageDataUrl; // Store for sending to backend

  // Update UI
  cameraPreview.classList.add("hidden");
  capturedImage.classList.remove("hidden");
  captureBtn.classList.add("hidden");
  retakeBtn.classList.remove("hidden");
  confirmCaptureBtn.classList.remove("hidden");

  // Stop video but keep modal open
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
  }
}

function retakePhoto() {
  // Reset and restart camera
  capturedImage.classList.add("hidden");
  cameraPreview.classList.remove("hidden");
  captureBtn.classList.remove("hidden");
  retakeBtn.classList.add("hidden");
  confirmCaptureBtn.classList.add("hidden");

  // Restart camera
  openCamera();
}

function confirmCapture() {
  closeCamera();

  // Get the captured image for this mode
  const imageToSend = lastCapturedImage;
  const imageType = currentCaptureMode; // "selfie" | "aadhaar_front" | "aadhaar_back"

  inputEl.value = "captured";

  // Re-enable input temporarily
  inputEl.disabled = false;
  sendBtn.disabled = false;
  inputEl.placeholder = "Processing...";

  // Send message with image data
  sendMessage(imageToSend, imageType);

  // Clear the stored image
  lastCapturedImage = null;
}

function closeCamera() {
  captureModal.classList.add("hidden");

  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }
}

// ========== New Chat ==========
function startNewChat() {
  if (confirm("Start a new conversation? Your current chat will be cleared.")) {
    chatEl.innerHTML = "";
    initThread();
    currentCaptureMode = null;
    // Re-enable input in case it was disabled
    inputEl.disabled = false;
    inputEl.placeholder = "Type your message...";
    sendBtn.disabled = false;
    updateAgentStatus("master");

    // Wait a moment then send empty message to trigger greeting
    setTimeout(() => {
      sendInitialGreeting();
    }, 100);
  }
}

async function sendInitialGreeting() {
  appendTypingIndicator();

  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        thread_id: threadId,
        user_message: "hi",
      }),
    });

    removeTypingIndicator();

    if (res.ok) {
      const data = await res.json();
      const bubble = appendMessage("assistant", data.assistant_message || "Hello! How can I help you?");

      if (data.current_agent) {
        updateAgentStatus(data.current_agent);
      }

      // Check for OTP notification
      if (data.otp_notification) {
        showOTPNotification(data.otp_notification);
      }

      // Check if OTP input is needed
      if (data.doc_verification_stage === "awaiting_otp") {
        renderOTPInput(bubble);
      } else {
        // Check for capture mode on initial greeting too
        checkForCaptureMode(data.assistant_message || "", bubble, data);
      }
    }
  } catch (err) {
    removeTypingIndicator();
    appendMessage("assistant", "Welcome! How can I help you with your personal loan needs today?");
  }
}

// ========== Event Listeners ==========
sendBtn.addEventListener("click", sendMessage);
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !inputEl.disabled) sendMessage();
});

// cameraBtn listener removed
closeCaptureBtn.addEventListener("click", closeCamera);
captureBtn.addEventListener("click", capturePhoto);
retakeBtn.addEventListener("click", retakePhoto);
confirmCaptureBtn.addEventListener("click", confirmCapture);
newChatBtn.addEventListener("click", startNewChat);

applyBtn.addEventListener("click", () => {
  inputEl.value = "Apply Loan";
  sendMessage();
});

// Close modal on escape key
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !captureModal.classList.contains("hidden")) {
    closeCamera();
  }
});

// ========== Initial Load ==========
sendInitialGreeting();

// ========== OTP Functions ==========
function renderOTPInput(bubbleEl) {
  isOTPMode = true;
  currentCaptureMode = null;

  // Disable main input while in OTP mode
  inputEl.disabled = true;
  inputEl.placeholder = "Enter OTP below...";
  sendBtn.disabled = true;

  // Create OTP input container
  const otpContainer = document.createElement("div");
  otpContainer.className = "otp-input-container";
  otpContainer.id = "otpInputContainer";

  // Create 6 digit input boxes
  for (let i = 0; i < 6; i++) {
    const input = document.createElement("input");
    input.type = "text";
    input.inputMode = "numeric";
    input.maxLength = 1;
    input.className = "otp-digit";
    input.id = `otp-digit-${i}`;
    input.dataset.index = i;

    // Event listeners for auto-advance
    input.addEventListener("input", handleOTPDigitInput);
    input.addEventListener("keydown", handleOTPKeyDown);
    input.addEventListener("paste", handleOTPPaste);

    otpContainer.appendChild(input);
  }

  // Create submit button
  const submitBtn = document.createElement("button");
  submitBtn.className = "otp-submit-btn";
  submitBtn.textContent = "Verify OTP";
  submitBtn.id = "otpSubmitBtn";
  submitBtn.disabled = true;
  submitBtn.onclick = submitOTP;

  // Create resend link
  const resendLink = document.createElement("a");
  resendLink.className = "otp-resend-link";
  resendLink.textContent = "Didn't receive the code? Resend OTP";
  resendLink.onclick = resendOTP;

  // Append to bubble
  bubbleEl.appendChild(document.createElement("br"));
  bubbleEl.appendChild(otpContainer);
  bubbleEl.appendChild(submitBtn);
  bubbleEl.appendChild(resendLink);

  // Focus first input
  setTimeout(() => {
    document.getElementById("otp-digit-0")?.focus();
  }, 100);

  // Scroll to bottom
  chatEl.scrollTop = chatEl.scrollHeight;
}

function handleOTPDigitInput(e) {
  const input = e.target;
  const index = parseInt(input.dataset.index);
  const value = input.value;

  // Only allow digits
  if (!/^\d*$/.test(value)) {
    input.value = "";
    return;
  }

  // Update filled state
  if (value) {
    input.classList.add("filled");
    input.classList.remove("error");

    // Auto-advance to next input
    if (index < 5) {
      const nextInput = document.getElementById(`otp-digit-${index + 1}`);
      nextInput?.focus();
    }
  } else {
    input.classList.remove("filled");
  }

  // Check if all digits are filled
  updateOTPSubmitState();
}

function handleOTPKeyDown(e) {
  const input = e.target;
  const index = parseInt(input.dataset.index);

  if (e.key === "Backspace" && !input.value && index > 0) {
    // Go to previous input on backspace if current is empty
    const prevInput = document.getElementById(`otp-digit-${index - 1}`);
    prevInput?.focus();
    e.preventDefault();
  } else if (e.key === "ArrowLeft" && index > 0) {
    const prevInput = document.getElementById(`otp-digit-${index - 1}`);
    prevInput?.focus();
  } else if (e.key === "ArrowRight" && index < 5) {
    const nextInput = document.getElementById(`otp-digit-${index + 1}`);
    nextInput?.focus();
  } else if (e.key === "Enter") {
    submitOTP();
  }
}

function handleOTPPaste(e) {
  e.preventDefault();
  const pastedData = e.clipboardData.getData("text").trim();

  // Extract only digits
  const digits = pastedData.replace(/\D/g, "").slice(0, 6);

  if (digits.length === 6) {
    for (let i = 0; i < 6; i++) {
      const input = document.getElementById(`otp-digit-${i}`);
      if (input) {
        input.value = digits[i];
        input.classList.add("filled");
      }
    }
    updateOTPSubmitState();
    document.getElementById("otp-digit-5")?.focus();
  }
}

function updateOTPSubmitState() {
  const submitBtn = document.getElementById("otpSubmitBtn");
  if (!submitBtn) return;

  let allFilled = true;
  for (let i = 0; i < 6; i++) {
    const input = document.getElementById(`otp-digit-${i}`);
    if (!input?.value) {
      allFilled = false;
      break;
    }
  }

  submitBtn.disabled = !allFilled;
}

function getOTPValue() {
  let otp = "";
  for (let i = 0; i < 6; i++) {
    const input = document.getElementById(`otp-digit-${i}`);
    otp += input?.value || "";
  }
  return otp;
}

async function submitOTP() {
  const otp = getOTPValue();

  if (otp.length !== 6) {
    // Show error state
    for (let i = 0; i < 6; i++) {
      const input = document.getElementById(`otp-digit-${i}`);
      if (input) input.classList.add("error");
    }
    return;
  }

  // Disable inputs while submitting
  const submitBtn = document.getElementById("otpSubmitBtn");
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = "Verifying...";
  }

  // Disable all OTP digit inputs
  for (let i = 0; i < 6; i++) {
    const input = document.getElementById(`otp-digit-${i}`);
    if (input) input.disabled = true;
  }

  appendTypingIndicator("Verifying OTP...");

  try {
    // Send OTP directly to backend - NOT via sendMessage() to avoid showing in chat
    const payload = {
      thread_id: threadId,
      user_message: otp,  // OTP code as the message
    };

    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    removeTypingIndicator();

    if (!res.ok) {
      appendMessage("assistant", "Error verifying OTP. Please try again.");
      resetOTPInputs();
      return;
    }

    const data = await res.json();
    const bubble = appendMessage("assistant", data.assistant_message || "(no reply)");

    // Update agent status
    if (data.current_agent) {
      updateAgentStatus(data.current_agent);
    }

    // Check if still in OTP stage (wrong OTP - allow retry)
    if (data.doc_verification_stage === "awaiting_otp") {
      // Clear OTP inputs for retry
      resetOTPInputs();
      renderOTPInput(bubble);
    } else {
      // OTP verified successfully - Update Button State
      if (submitBtn) {
        submitBtn.textContent = "Verified";
        submitBtn.classList.add("verified");
        // Keep disabled
      }

      // OTP verified or stage changed - exit OTP mode
      isOTPMode = false;
      inputEl.disabled = false;
      inputEl.placeholder = "Type your message...";
      sendBtn.disabled = false;

      // Check if we need to render document upload UI
      if (data.doc_verification_stage === "document_upload") {
        // Store customer UUID for document uploads
        if (data.customer_uuid) {
          customerUUID = data.customer_uuid;
        }
        // Render document upload UI
        if (data.required_documents && data.required_documents.length > 0) {
          renderDocumentUploadUI(bubble, data.required_documents, data.uploaded_documents);
        }
      }
    }

  } catch (e) {
    removeTypingIndicator();
    appendMessage("assistant", "Connection error. Please try again.");
    resetOTPInputs();
  }
}

function resetOTPInputs() {
  const submitBtn = document.getElementById("otpSubmitBtn");
  if (submitBtn) {
    submitBtn.disabled = false;
    submitBtn.textContent = "Verify OTP";
  }
  for (let i = 0; i < 6; i++) {
    const input = document.getElementById(`otp-digit-${i}`);
    if (input) {
      input.disabled = false;
      input.value = "";
      input.classList.remove("filled", "error");
    }
  }
  document.getElementById("otp-digit-0")?.focus();
}

async function resendOTP() {
  // Clear OTP inputs
  resetOTPInputs();

  appendTypingIndicator("Sending new OTP...");

  try {
    // Send resend request directly - NOT via sendMessage()
    const payload = {
      thread_id: threadId,
      user_message: "resend",
    };

    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    removeTypingIndicator();

    if (!res.ok) {
      appendMessage("assistant", "Error resending OTP. Please try again.");
      return;
    }

    const data = await res.json();
    const bubble = appendMessage("assistant", data.assistant_message || "(no reply)");

    // Re-render OTP input
    if (data.doc_verification_stage === "awaiting_otp") {
      renderOTPInput(bubble);
    }

  } catch (e) {
    removeTypingIndicator();
    appendMessage("assistant", "Connection error. Please try again.");
  }
}

function showOTPNotification(otp) {
  if (!otpNotification || !otpNotificationCode) return;

  // Set OTP code with spacing
  const formattedOTP = otp.split("").join(" ");
  otpNotificationCode.textContent = formattedOTP;

  // Show notification
  otpNotification.classList.add("show");

  // Auto-hide after 15 seconds
  setTimeout(() => {
    hideOTPNotification();
  }, 15000);
}

function hideOTPNotification() {
  if (otpNotification) {
    otpNotification.classList.remove("show");
  }
}

// Make hideOTPNotification globally available for the HTML onclick
window.hideOTPNotification = hideOTPNotification;

// ========== Document Upload Functions ==========

function renderDocumentUploadUI(bubble, documents, uploadStatus) {
  if (!documents || documents.length === 0) return;

  // Store for later reference
  requiredDocuments = documents;
  uploadedDocuments = uploadStatus || {};

  // Create container
  const container = document.createElement("div");
  container.className = "document-upload-container";
  container.id = "documentUploadContainer";

  // Create upload box for each document
  documents.forEach(doc => {
    const isUploaded = uploadedDocuments[doc.id] === true;

    const box = document.createElement("div");
    box.className = "document-upload-box";
    box.id = `doc-box-${doc.id}`;

    box.innerHTML = `
      <div class="document-info">
        <span class="document-name">${doc.name}</span>
        <span class="document-description">${doc.description}</span>
      </div>
      <div class="document-actions">
        <button class="upload-btn ${isUploaded ? 'uploaded' : ''}" 
                id="upload-btn-${doc.id}"
                ${isUploaded ? 'disabled' : ''}>
          ${isUploaded ? 'Uploaded' : 'Upload'}
        </button>
        <div class="document-status ${isUploaded ? 'complete' : 'pending'}" 
             id="status-${doc.id}"></div>
      </div>
      <input type="file" 
             class="hidden-file-input" 
             id="file-input-${doc.id}" 
             accept=".pdf,application/pdf">
    `;

    container.appendChild(box);

    // Add click handler for upload button
    setTimeout(() => {
      const uploadBtn = document.getElementById(`upload-btn-${doc.id}`);
      const fileInput = document.getElementById(`file-input-${doc.id}`);

      if (uploadBtn && fileInput) {
        uploadBtn.addEventListener("click", () => fileInput.click());
        fileInput.addEventListener("change", (e) => handleFileSelect(e, doc.id));
      }
    }, 0);
  });

  // Add proceed button
  const proceedSection = document.createElement("div");
  proceedSection.className = "proceed-section";

  const allComplete = documents.every(d => uploadedDocuments[d.id] === true);
  proceedSection.innerHTML = `
    <button class="proceed-btn ${allComplete ? 'active' : ''}" 
            id="proceedBtn"
            ${allComplete ? '' : 'disabled'}>
      Proceed
    </button>
  `;
  container.appendChild(proceedSection);

  // Add to bubble
  bubble.appendChild(container);

  // Add proceed handler
  setTimeout(() => {
    const proceedBtn = document.getElementById("proceedBtn");
    if (proceedBtn) {
      proceedBtn.addEventListener("click", handleProceed);
    }
  }, 0);

  chatEl.scrollTop = chatEl.scrollHeight;
}

async function handleFileSelect(event, docType) {
  const file = event.target.files[0];
  if (!file) return;

  // Validate PDF
  if (file.type !== "application/pdf") {
    alert("Please select a PDF file.");
    return;
  }

  // Update UI to show processing
  const uploadBtn = document.getElementById(`upload-btn-${docType}`);
  const statusEl = document.getElementById(`status-${docType}`);

  if (uploadBtn) {
    uploadBtn.disabled = true;
    uploadBtn.textContent = "Uploading...";
  }
  if (statusEl) {
    statusEl.className = "document-status processing";
  }

  try {
    // Convert to base64
    const base64 = await fileToBase64(file);

    // Upload to backend
    const response = await fetch(UPLOAD_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        thread_id: threadId,
        customer_uuid: customerUUID,
        doc_type: docType,
        pdf_base64: base64,
      }),
    });

    const data = await response.json();

    if (data.success) {
      // Update local state
      uploadedDocuments[docType] = true;

      // Update UI
      if (uploadBtn) {
        uploadBtn.textContent = "Uploaded";
        uploadBtn.classList.add("uploaded");
      }
      if (statusEl) {
        statusEl.className = "document-status complete";
      }

      // Check if all complete
      checkAllDocumentsUploaded();
    } else {
      // Upload failed
      if (uploadBtn) {
        uploadBtn.disabled = false;
        uploadBtn.textContent = "Retry";
      }
      if (statusEl) {
        statusEl.className = "document-status pending";
      }
      alert(`Upload failed: ${data.message}`);
    }

  } catch (error) {
    console.error("Upload error:", error);
    if (uploadBtn) {
      uploadBtn.disabled = false;
      uploadBtn.textContent = "Retry";
    }
    if (statusEl) {
      statusEl.className = "document-status pending";
    }
    alert("Upload failed. Please try again.");
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => resolve(reader.result);
    reader.onerror = (error) => reject(error);
  });
}

function checkAllDocumentsUploaded() {
  const allComplete = requiredDocuments.every(d => uploadedDocuments[d.id] === true);
  const proceedBtn = document.getElementById("proceedBtn");

  if (proceedBtn) {
    if (allComplete) {
      proceedBtn.classList.add("active");
      proceedBtn.disabled = false;
    } else {
      proceedBtn.classList.remove("active");
      proceedBtn.disabled = true;
    }
  }
}

async function handleProceed() {
  const proceedBtn = document.getElementById("proceedBtn");

  // Check if all uploaded
  const allComplete = requiredDocuments.every(d => uploadedDocuments[d.id] === true);
  if (!allComplete) {
    alert("Please upload all required documents before proceeding.");
    return;
  }

  // Disable button
  if (proceedBtn) {
    proceedBtn.disabled = true;
    proceedBtn.textContent = "Processing...";
  }

  // Print statement for future agent integration
  console.log("[Document Upload] All documents uploaded. Proceeding...");
  console.log("[Document Upload] Customer UUID:", customerUUID);
  console.log("[Document Upload] Uploaded documents:", uploadedDocuments);

  // Send proceed message to backend
  appendTypingIndicator("Finalizing your application...");

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        thread_id: threadId,
        user_message: "proceed",
      }),
    });

    removeTypingIndicator();

    if (response.ok) {
      const data = await response.json();
      const bubble = appendMessage("assistant", data.assistant_message || "Thank you!");

      // Store customer UUID if provided (needed for re-uploads)
      if (data.customer_uuid) {
        customerUUID = data.customer_uuid;
      }

      // Check for retry stages and render appropriate upload UI
      const stage = data.doc_verification_stage;

      if (stage === "pan_retry") {
        renderPANRetryUI(bubble);
      } else if (stage === "employment_retry") {
        renderDocRetryUI(bubble, "employment_certificate", "Employment Certificate");
      } else if (stage === "salary_retry") {
        renderDocRetryUI(bubble, "salary_slips", "Salary Slips");
      } else if (stage === "bank_retry") {
        renderDocRetryUI(bubble, "bank_statements", "Bank Statements");
      } else if (stage === "address_retry") {
        renderDocRetryUI(bubble, "address_proof", "Address Proof");
      } else if (stage === "loan_approved" && data.underwriting_result) {
        // Render aesthetic loan approval UI
        renderLoanApprovalUI(bubble, data.underwriting_result);
      } else if (stage === "complete" || stage === "verification_rejected") {
        // Verification flow complete (approved or rejected)
        customerUUID = null;
        uploadedDocuments = {};
        requiredDocuments = [];

        // Re-enable input
        inputEl.disabled = false;
        inputEl.placeholder = "Type your message...";
        sendBtn.disabled = false;
      }
      // For other stages, keep the UI as-is (flow continues)
    }
  } catch (error) {
    removeTypingIndicator();
    appendMessage("assistant", "There was an error. Please try again.");
    if (proceedBtn) {
      proceedBtn.disabled = false;
      proceedBtn.textContent = "Proceed";
    }
  }
}

// ========== PAN Retry UI ==========
function renderPANRetryUI(bubble) {
  // Create container for single PAN upload
  const container = document.createElement("div");
  container.className = "document-upload-container";
  container.id = "panRetryContainer";

  // Single PAN upload box
  const panDoc = {
    id: "pan_card",
    name: "PAN Card",
    description: "Re-upload a clear image of your PAN"
  };

  const box = document.createElement("div");
  box.className = "document-upload-box";
  box.id = `doc-box-${panDoc.id}`;

  box.innerHTML = `
    <div class="document-info">
      <span class="document-name">${panDoc.name}</span>
      <span class="document-description">${panDoc.description}</span>
    </div>
    <div class="document-actions">
      <button class="upload-btn" id="upload-btn-pan-retry">
        Re-upload
      </button>
      <div class="document-status pending" id="status-pan-retry"></div>
    </div>
    <input type="file" 
           class="hidden-file-input" 
           id="file-input-pan-retry" 
           accept=".pdf,application/pdf">
  `;

  container.appendChild(box);

  // Add proceed button (right-aligned)
  const proceedSection = document.createElement("div");
  proceedSection.className = "proceed-section";
  proceedSection.innerHTML = `
    <button class="proceed-btn" id="panRetryProceedBtn" disabled>
      Verify PAN
    </button>
  `;
  container.appendChild(proceedSection);

  // Add to bubble
  bubble.appendChild(container);

  // Add event handlers
  setTimeout(() => {
    const uploadBtn = document.getElementById("upload-btn-pan-retry");
    const fileInput = document.getElementById("file-input-pan-retry");
    const proceedBtn = document.getElementById("panRetryProceedBtn");

    if (uploadBtn && fileInput) {
      uploadBtn.addEventListener("click", () => fileInput.click());
      fileInput.addEventListener("change", (e) => handlePANRetryFileSelect(e));
    }

    if (proceedBtn) {
      proceedBtn.addEventListener("click", handlePANRetryProceed);
    }
  }, 0);

  chatEl.scrollTop = chatEl.scrollHeight;
}

async function handlePANRetryFileSelect(event) {
  const file = event.target.files[0];
  if (!file) return;

  // Validate PDF
  if (file.type !== "application/pdf") {
    alert("Please select a PDF file.");
    return;
  }

  // Update UI
  const uploadBtn = document.getElementById("upload-btn-pan-retry");
  const statusEl = document.getElementById("status-pan-retry");
  const proceedBtn = document.getElementById("panRetryProceedBtn");

  if (uploadBtn) {
    uploadBtn.disabled = true;
    uploadBtn.textContent = "Uploading...";
  }
  if (statusEl) {
    statusEl.className = "document-status processing";
  }

  try {
    // Convert to base64
    const base64 = await fileToBase64(file);

    // Upload to backend
    const response = await fetch(UPLOAD_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        thread_id: threadId,
        customer_uuid: customerUUID,
        doc_type: "pan_card",
        pdf_base64: base64,
      }),
    });

    const data = await response.json();

    if (data.success) {
      // Update UI
      if (uploadBtn) {
        uploadBtn.textContent = "Uploaded";
        uploadBtn.classList.add("uploaded");
      }
      if (statusEl) {
        statusEl.className = "document-status complete";
      }
      if (proceedBtn) {
        proceedBtn.classList.add("active");
        proceedBtn.disabled = false;
      }
    } else {
      // Upload failed
      if (uploadBtn) {
        uploadBtn.disabled = false;
        uploadBtn.textContent = "Retry";
      }
      if (statusEl) {
        statusEl.className = "document-status pending";
      }
      alert(`Upload failed: ${data.message}`);
    }

  } catch (error) {
    console.error("Upload error:", error);
    if (uploadBtn) {
      uploadBtn.disabled = false;
      uploadBtn.textContent = "Retry";
    }
    if (statusEl) {
      statusEl.className = "document-status pending";
    }
    alert("Upload failed. Please try again.");
  }
}

async function handlePANRetryProceed() {
  const proceedBtn = document.getElementById("panRetryProceedBtn");

  if (proceedBtn) {
    proceedBtn.disabled = true;
    proceedBtn.textContent = "Verifying...";
  }

  appendTypingIndicator("Verifying your PAN...");

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        thread_id: threadId,
        user_message: "pan_reuploaded",
      }),
    });

    removeTypingIndicator();

    if (response.ok) {
      const data = await response.json();
      const bubble = appendMessage("assistant", data.assistant_message || "Processing...");

      // Check for pan_retry again (another failure) or completion
      if (data.doc_verification_stage === "pan_retry") {
        // Still needs retry
        renderPANRetryUI(bubble);
      } else if (data.doc_verification_stage === "pan_rejected") {
        // Final rejection - nothing more to render
        inputEl.disabled = false;
        inputEl.placeholder = "Type your message...";
        sendBtn.disabled = false;
      } else {
        // Success or other stage
        inputEl.disabled = false;
        inputEl.placeholder = "Type your message...";
        sendBtn.disabled = false;
      }
    }
  } catch (error) {
    removeTypingIndicator();
    appendMessage("assistant", "There was an error. Please try again.");
    if (proceedBtn) {
      proceedBtn.disabled = false;
      proceedBtn.textContent = "Verify PAN";
    }
  }
}

// ========== Generic Document Retry UI ==========
function renderDocRetryUI(bubble, docType, docName) {
  const container = document.createElement("div");
  container.className = "document-retry-container";
  container.id = `${docType}RetryContainer`;

  const box = document.createElement("div");
  box.className = "document-retry-box";
  box.id = `doc-box-${docType}-retry`;

  box.innerHTML = `
    <div class="document-info">
      <span class="document-name">${docName}</span>
      <span class="document-description">Re-upload a clear document</span>
    </div>
    <div class="document-actions">
      <button class="upload-btn" id="upload-btn-${docType}-retry">
        Re-upload
      </button>
      <div class="document-status pending" id="status-${docType}-retry"></div>
    </div>
    <input type="file" 
           class="hidden-file-input" 
           id="file-input-${docType}-retry" 
           accept=".pdf,application/pdf">
  `;

  container.appendChild(box);

  const proceedSection = document.createElement("div");
  proceedSection.className = "proceed-section";
  proceedSection.innerHTML = `
    <button class="proceed-btn" id="${docType}RetryProceedBtn" disabled>
      Verify
    </button>
  `;
  container.appendChild(proceedSection);

  bubble.appendChild(container);

  setTimeout(() => {
    const uploadBtn = document.getElementById(`upload-btn-${docType}-retry`);
    const fileInput = document.getElementById(`file-input-${docType}-retry`);
    const proceedBtn = document.getElementById(`${docType}RetryProceedBtn`);

    if (uploadBtn && fileInput) {
      uploadBtn.addEventListener("click", () => fileInput.click());
      fileInput.addEventListener("change", (e) => handleDocRetryFileSelect(e, docType));
    }

    if (proceedBtn) {
      proceedBtn.addEventListener("click", () => handleDocRetryProceed(docType));
    }
  }, 0);

  chatEl.scrollTop = chatEl.scrollHeight;
}

async function handleDocRetryFileSelect(event, docType) {
  const file = event.target.files[0];
  if (!file) return;

  if (file.type !== "application/pdf") {
    alert("Please select a PDF file.");
    return;
  }

  const uploadBtn = document.getElementById(`upload-btn-${docType}-retry`);
  const statusEl = document.getElementById(`status-${docType}-retry`);
  const proceedBtn = document.getElementById(`${docType}RetryProceedBtn`);

  if (uploadBtn) {
    uploadBtn.disabled = true;
    uploadBtn.textContent = "Uploading...";
  }
  if (statusEl) {
    statusEl.className = "document-status processing";
  }

  try {
    const base64 = await fileToBase64(file);

    const response = await fetch(UPLOAD_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        thread_id: threadId,
        customer_uuid: customerUUID,
        doc_type: docType,
        pdf_base64: base64,
      }),
    });

    const data = await response.json();

    if (data.success) {
      if (uploadBtn) {
        uploadBtn.textContent = "Uploaded";
        uploadBtn.classList.add("uploaded");
      }
      if (statusEl) {
        statusEl.className = "document-status complete";
      }
      if (proceedBtn) {
        proceedBtn.classList.add("active");
        proceedBtn.disabled = false;
      }
    } else {
      if (uploadBtn) {
        uploadBtn.disabled = false;
        uploadBtn.textContent = "Retry";
      }
      if (statusEl) {
        statusEl.className = "document-status pending";
      }
      alert(`Upload failed: ${data.message}`);
    }
  } catch (error) {
    console.error("Upload error:", error);
    if (uploadBtn) {
      uploadBtn.disabled = false;
      uploadBtn.textContent = "Retry";
    }
    if (statusEl) {
      statusEl.className = "document-status pending";
    }
    alert("Upload failed. Please try again.");
  }
}

async function handleDocRetryProceed(docType) {
  const proceedBtn = document.getElementById(`${docType}RetryProceedBtn`);

  if (proceedBtn) {
    proceedBtn.disabled = true;
    proceedBtn.textContent = "Verifying...";
  }

  appendTypingIndicator("Verifying your document...");

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        thread_id: threadId,
        user_message: "doc_reuploaded",
      }),
    });

    removeTypingIndicator();

    if (response.ok) {
      const data = await response.json();
      const bubble = appendMessage("assistant", data.assistant_message || "Processing...");

      // Store customer UUID if provided
      if (data.customer_uuid) {
        customerUUID = data.customer_uuid;
      }

      // Check for another retry or completion
      if (data.doc_verification_stage && data.doc_verification_stage.endsWith("_retry")) {
        // Another document needs retry
        const newDocType = data.doc_verification_stage.replace("_retry", "");
        const docNames = {
          "employment": "Employment Certificate",
          "salary": "Salary Slips",
          "bank": "Bank Statements",
          "address": "Address Proof"
        };
        const mapping = {
          "employment": "employment_certificate",
          "salary": "salary_slips",
          "bank": "bank_statements",
          "address": "address_proof"
        };
        renderDocRetryUI(bubble, mapping[newDocType] || docType, docNames[newDocType] || "Document");
      } else {
        inputEl.disabled = false;
        inputEl.placeholder = "Type your message...";
        sendBtn.disabled = false;
      }
    }
  } catch (error) {
    removeTypingIndicator();
    appendMessage("assistant", "There was an error. Please try again.");
    if (proceedBtn) {
      proceedBtn.disabled = false;
      proceedBtn.textContent = "Verify";
    }
  }
}

// ========== Loan Approval UI ==========

function formatCurrency(amount) {
  if (!amount) return "₹0";
  const str = amount.toString();
  let result = str.slice(-3);
  let remaining = str.slice(0, -3);
  while (remaining.length > 0) {
    result = remaining.slice(-2) + "," + result;
    remaining = remaining.slice(0, -2);
  }
  return "₹" + result;
}

function renderLoanApprovalUI(bubble, result) {
  // Clear the placeholder text (__LOAN_APPROVED__) from the bubble
  bubble.innerHTML = "";

  const container = document.createElement("div");
  container.className = "loan-approval-container";
  container.id = "loanApprovalContainer";

  const breakdown = result.score_breakdown || {};

  container.innerHTML = `
    <div class="approval-header">
      <p class="approved-badge">APPROVED</p>
      <h2>Congratulations, ${result.customer_name}!</h2>
      <p class="subtitle">Your personal loan application has been approved</p>
    </div>
    
    <div class="approval-body">
      <div class="score-section">
        <div class="score-badge">
          <span class="score-value">${result.score}/100</span>
          <span class="score-label">Underwriting Score</span>
        </div>
        
        <div class="score-breakdown">
          <div class="score-item">
            <span class="label">CIBIL Score</span>
            <span class="value">${breakdown.cibil || 0}/40</span>
          </div>
          <div class="score-item">
            <span class="label">FOIR</span>
            <span class="value">${breakdown.foir || 0}/30</span>
          </div>
          <div class="score-item">
            <span class="label">Employment</span>
            <span class="value">${breakdown.employment || 0}/15</span>
          </div>
          <div class="score-item">
            <span class="label">Income Verification</span>
            <span class="value">${breakdown.income || 0}/10</span>
          </div>
          <div class="score-item">
            <span class="label">Bank Balance</span>
            <span class="value">${breakdown.bank || 0}/5</span>
          </div>
        </div>
      </div>
      
      <div class="loan-details-section">
        <span class="section-title">Loan Details</span>
        <table class="loan-details-table">
          <tr>
            <td>Loan Amount</td>
            <td>${formatCurrency(result.loan_amount)}</td>
          </tr>
          <tr>
            <td>Interest Rate</td>
            <td>${result.interest_rate?.toFixed(2) || "16.00"}% p.a.</td>
          </tr>
          <tr>
            <td>Tenure</td>
            <td>${result.tenure_months} months</td>
          </tr>
          <tr>
            <td>Monthly EMI</td>
            <td>${formatCurrency(result.emi)}</td>
          </tr>
          <tr>
            <td>Processing Fee (1.5%)</td>
            <td>${formatCurrency(result.processing_fee)}</td>
          </tr>
          <tr>
            <td>Total Interest</td>
            <td>${formatCurrency(result.total_interest)}</td>
          </tr>
          <tr>
            <td><strong>Total Payable</strong></td>
            <td><strong>${formatCurrency(result.total_payable)}</strong></td>
          </tr>
        </table>
        
        <ul class="loan-terms-list">
          <li>EMI will be deducted on the same date each month</li>
          <li>First EMI is due 30 days from disbursement</li>
          <li>Prepayment allowed after 6 months (no charges)</li>
          <li>Loan agreement will be sent via email</li>
        </ul>
      </div>
      
      <div class="loan-action-buttons">
        <button class="btn-accept" id="btnAcceptLoan">Accept Offer</button>
        <button class="btn-decline" id="btnDeclineLoan">Decline</button>
      </div>
    </div>
  `;

  bubble.appendChild(container);

  // Add event listeners
  setTimeout(() => {
    const acceptBtn = document.getElementById("btnAcceptLoan");
    const declineBtn = document.getElementById("btnDeclineLoan");

    if (acceptBtn) {
      acceptBtn.addEventListener("click", handleAcceptLoan);
    }
    if (declineBtn) {
      declineBtn.addEventListener("click", showDeclineConfirmation);
    }
  }, 0);

  chatEl.scrollTop = chatEl.scrollHeight;
}

function showDeclineConfirmation() {
  const modal = document.createElement("div");
  modal.className = "confirmation-modal";
  modal.id = "declineModal";
  modal.innerHTML = `
    <div class="confirmation-box">
      <h3>Are you sure?</h3>
      <p>You are about to decline this loan offer. This action cannot be undone.</p>
      <div class="btn-group">
        <button class="btn-cancel" id="btnCancelDecline">Cancel</button>
        <button class="btn-confirm-decline" id="btnConfirmDecline">Yes, Decline</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  document.getElementById("btnCancelDecline").addEventListener("click", () => {
    document.getElementById("declineModal").remove();
  });

  document.getElementById("btnConfirmDecline").addEventListener("click", async () => {
    document.getElementById("declineModal").remove();
    await handleDeclineLoan();
  });
}

async function handleDeclineLoan() {
  const container = document.getElementById("loanApprovalContainer");
  if (container) {
    container.innerHTML = `
      <div class="declined-message">
        <h3>Loan Offer Declined</h3>
        <p>You chose to decline the loan offer. Thank you for considering Tata Capital.</p>
      </div>
    `;
  }

  // Also call API
  try {
    await fetch(LOAN_DECISION_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        thread_id: threadId,
        decision: "decline"
      })
    });
  } catch (e) {
    console.error("Failed to record decline:", e);
  }

  // Re-enable chat
  inputEl.disabled = false;
  inputEl.placeholder = "Type your message...";
  sendBtn.disabled = false;
}

async function handleAcceptLoan() {
  const acceptBtn = document.getElementById("btnAcceptLoan");
  const declineBtn = document.getElementById("btnDeclineLoan");

  if (acceptBtn) {
    acceptBtn.disabled = true;
    acceptBtn.textContent = "Processing...";
  }
  if (declineBtn) {
    declineBtn.style.display = "none";
  }

  try {
    const response = await fetch(LOAN_DECISION_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        thread_id: threadId,
        decision: "accept"
      })
    });

    const data = await response.json();

    if (data.success && data.pdf_base64) {
      // Render sanction letter card
      renderSanctionLetterCard(data);
    }
  } catch (error) {
    console.error("Accept loan error:", error);
    if (acceptBtn) {
      acceptBtn.disabled = false;
      acceptBtn.textContent = "Accept Offer";
    }
    if (declineBtn) {
      declineBtn.style.display = "block";
    }
    alert("Failed to process. Please try again.");
  }
}

function renderSanctionLetterCard(data) {
  const container = document.getElementById("loanApprovalContainer");
  if (!container) return;

  // Hide action buttons
  const buttons = container.querySelector(".loan-action-buttons");
  if (buttons) {
    buttons.style.display = "none";
  }

  // Create sanction letter card
  const card = document.createElement("div");
  card.className = "sanction-letter-card";
  card.innerHTML = `
    <div class="card-header">
      <div class="pdf-icon">PDF</div>
      <div class="file-info">
        <h4>${data.pdf_filename}</h4>
        <p>Reference: ${data.reference_number}</p>
      </div>
    </div>
    <button class="download-btn" id="downloadSanctionLetter">
      <span>📥</span> Download Sanction Letter
    </button>
    
    <div class="email-prompt" id="emailPrompt">
      <p><strong>Would you like us to email the sanction letter?</strong></p>
      <div class="btn-group">
        <button class="btn-yes" id="btnEmailYes">Yes</button>
        <button class="btn-no" id="btnEmailNo">No, thanks</button>
      </div>
    </div>
  `;

  container.querySelector(".approval-body").appendChild(card);

  // Store PDF data for download
  window.sanctionLetterPDF = data.pdf_base64;
  window.sanctionLetterFilename = data.pdf_filename;

  // Event listeners
  document.getElementById("downloadSanctionLetter").addEventListener("click", downloadSanctionLetter);
  document.getElementById("btnEmailYes").addEventListener("click", showEmailInput);
  document.getElementById("btnEmailNo").addEventListener("click", () => {
    document.getElementById("emailPrompt").innerHTML = `
      <p style="color: var(--success); font-weight: 600;">✓ No problem! You can download the letter above.</p>
    `;
    completeFlow();
  });

  chatEl.scrollTop = chatEl.scrollHeight;
}

function downloadSanctionLetter() {
  if (window.sanctionLetterPDF) {
    const link = document.createElement("a");
    link.href = `data:application/pdf;base64,${window.sanctionLetterPDF}`;
    link.download = window.sanctionLetterFilename || "Sanction_Letter.pdf";
    link.click();
  }
}

function showEmailInput() {
  const prompt = document.getElementById("emailPrompt");
  if (!prompt) return;

  prompt.innerHTML = `
    <div class="email-input-section">
      <input type="email" id="emailInput" placeholder="Enter your email address" />
      <button class="btn-send" id="btnSendEmail">Send Email</button>
    </div>
  `;

  document.getElementById("btnSendEmail").addEventListener("click", async () => {
    const email = document.getElementById("emailInput").value.trim();
    if (!email || !email.includes("@")) {
      alert("Please enter a valid email address.");
      return;
    }

    document.getElementById("btnSendEmail").disabled = true;
    document.getElementById("btnSendEmail").textContent = "Sending...";

    // Mock email sending
    await new Promise(resolve => setTimeout(resolve, 1500));

    prompt.innerHTML = `
      <p style="color: var(--success); font-weight: 600;">✓ Sanction letter sent to ${email}</p>
    `;

    completeFlow();
  });
}

function completeFlow() {
  // Re-enable chat after a brief delay
  setTimeout(() => {
    inputEl.disabled = false;
    inputEl.placeholder = "Type your message...";
    sendBtn.disabled = false;

    appendMessage("assistant", "Thank you for choosing **Tata Capital**! Our representative will contact you within 24 hours to complete the formalities. If you have any questions, feel free to ask.");
  }, 1000);
}
