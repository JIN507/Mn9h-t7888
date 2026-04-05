import { createContext, useContext, useState, useEffect } from 'react';
import apiClient from '../services/apiClient';

const AuthContext = createContext();

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [token, setToken] = useState(localStorage.getItem('token'));
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const initAuth = async () => {
            if (token) {
                try {
                    apiClient.defaults.headers.common['Authorization'] = `Bearer ${token}`;
                    const response = await apiClient.get('/api/auth/me');
                    if (response.data.success) {
                        setUser(response.data.user);
                    }
                } catch (error) {
                    console.error('Auth init failed:', error);
                    logout();
                }
            }
            setLoading(false);
        };

        initAuth();
    }, [token]);

    const login = async (email, password) => {
        const response = await apiClient.post('/api/auth/login', { email, password });
        if (response.data.success) {
            const newToken = response.data.token;
            localStorage.setItem('token', newToken);
            setToken(newToken);
            setUser(response.data.user);
            apiClient.defaults.headers.common['Authorization'] = `Bearer ${newToken}`;
            return true;
        }
        return false;
    };

    const register = async (name, email, password) => {
        const response = await apiClient.post('/api/auth/register', {
            display_name: name,
            email,
            password
        });
        if (response.data.success) {
            const newToken = response.data.token;
            localStorage.setItem('token', newToken);
            setToken(newToken);
            setUser(response.data.user);
            apiClient.defaults.headers.common['Authorization'] = `Bearer ${newToken}`;
            return true;
        }
        return false;
    };

    const logout = () => {
        localStorage.removeItem('token');
        setToken(null);
        setUser(null);
        delete apiClient.defaults.headers.common['Authorization'];
    };

    const value = {
        user,
        token,
        loading,
        login,
        register,
        logout,
        isAuthenticated: !!user,
        isAdmin: user?.is_admin || false
    };

    return (
        <AuthContext.Provider value={value}>
            {!loading && children}
        </AuthContext.Provider>
    );
};
