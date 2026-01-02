import axios from 'axios';
import { auth } from '../firebase';

const api = axios.create({
  // AUTO-DETECT BACKEND:
  // 1. If we are on Cloudflare (hostname contains 'trycloudflare.com'), use RELATIVE path (API is proxied).
  // 2. Otherwise default to Environment Variable or Localhost.
  baseURL: window.location.hostname.includes('trycloudflare.com') 
      ? '/' 
      : (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'),
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
