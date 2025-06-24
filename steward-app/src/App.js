import React, { useState } from "react";
import Finances from "./finances";
import ToastModal from "./ToastModal";
import './App.css';

function App() {
  const [toast, setToast] = useState({ open: false, message: "", type: "info" });

  function showModal(message, type = "info") {
    setToast({ open: true, message, type });
    setTimeout(() => setToast((t) => ({ ...t, open: false })), 2000); // chiude dopo 2 secondi
  }

  return (
    <div className="App">
      <header className="App-header">
        <img src={logo} className="App-logo" alt="logo" />
        <p>
          Edit <code>src/App.js</code> and save to reload.
        </p>
        <a
          className="App-link"
          href="https://reactjs.org"
          target="_blank"
          rel="noopener noreferrer"
        >
          Learn React
        </a>
      </header>
      <Finances showModal={showModal} />
      <ToastModal
        open={toast.open}
        message={toast.message}
        type={toast.type}
        onClose={() => setToast((t) => ({ ...t, open: false }))}
      />
    </div>
  );
}

export default App;
