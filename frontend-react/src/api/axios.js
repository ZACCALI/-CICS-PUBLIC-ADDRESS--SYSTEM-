import axios from 'axios';
import { auth } from '../firebase';

const api = axios.create({
  // AUTO-DETECT BACKEND:
  // If we are served by the backend (Production), use relative path.
  // We only need absolute URL for local dev (npm run dev vs python app.py)
  baseURL: import.meta.env.DEV ? (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000') : '/',
});

// Request interceptor to add the Firebase Token to requests
api.interceptors.request.use(async (config) => {
  const user = auth.currentUser;
  if (user) {
    const token = await user.getIdToken();
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}, (error) => {
  return Promise.reject(error);
});

export default api;
