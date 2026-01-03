import axios from 'axios';
import { auth } from '../firebase';

// 1. Determine Base URL
// - If VITE_API_BASE_URL is set (e.g. .env), use it.
// - If we are in Development (npm run dev), default to localhost:8000.
// - If we are in Production (built app served by Backend), use relative path '/' to hit the same device.
const getBaseUrl = () => {
  if (import.meta.env.VITE_API_BASE_URL) return import.meta.env.VITE_API_BASE_URL;
  if (import.meta.env.MODE === 'development') return 'http://localhost:8000';
  return ''; // Relative path (Same Origin)
};

const api = axios.create({
  baseURL: getBaseUrl(),
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
