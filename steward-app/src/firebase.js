import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";

// Sostituisci questi valori con quelli del tuo progetto Firebase!
const firebaseConfig = {
  apiKey: "INSERISCI_LA_TUA_API_KEY",
  authDomain: "INSERISCI_LA_TUA_AUTH_DOMAIN",
  projectId: "INSERISCI_LA_TUA_PROJECT_ID",
  storageBucket: "INSERISCI_LA_TUA_STORAGE_BUCKET",
  messagingSenderId: "INSERISCI_LA_TUA_MESSAGING_SENDER_ID",
  appId: "INSERISCI_LA_TUA_APP_ID"
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

export { db };