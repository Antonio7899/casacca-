// src/ToastModal.jsx
import React from "react";

const toastStyles = {
  position: "fixed",
  bottom: "30px",
  right: "30px",
  minWidth: "220px",
  padding: "16px 24px",
  borderRadius: "8px",
  color: "#fff",
  fontWeight: "bold",
  fontSize: "1rem",
  zIndex: 9999,
  boxShadow: "0 2px 12px rgba(0,0,0,0.15)",
  transition: "opacity 0.3s",
};

const typeColors = {
  success: "#2ecc40",
  error: "#ff4136",
  info: "#0074d9",
  warning: "#ff851b",
};

export default function ToastModal({ open, message, type = "info", onClose }) {
  if (!open) return null;
  return (
    <div
      style={{
        ...toastStyles,
        background: typeColors[type] || "#333",
        opacity: open ? 1 : 0,
      }}
      onClick={onClose}
    >
      {message}
    </div>
  );
}