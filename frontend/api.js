const API_BASE_URL = window.API_BASE_URL || localStorage.getItem('internetDetectiveApi') || 'http://localhost:8000';
async function api(path, options = {}) { const res = await fetch(API_BASE_URL + path, {headers:{'Content-Type':'application/json'}, ...options}); if (!res.ok) throw new Error((await res.json().catch(()=>({}))).detail || `Request failed (${res.status})`); return res.json(); }
