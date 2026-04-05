import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import GradientButton from '../components/GradientButton';
import { Users, Lock, Search, AlertCircle, CheckCircle, RefreshCw } from 'lucide-react';

const AdminDashboard = () => {
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const { isAdmin } = useAuth();

    // Password Reset State
    const [selectedUser, setSelectedUser] = useState(null);
    const [newPassword, setNewPassword] = useState('');
    const [resetLoading, setResetLoading] = useState(false);

    useEffect(() => {
        if (isAdmin) {
            fetchUsers();
        }
    }, [isAdmin]);

    const fetchUsers = async () => {
        setLoading(true);
        try {
            const response = await apiClient.get('/api/admin/users');
            if (response.data.success) {
                setUsers(response.data.users);
            }
        } catch (err) {
            setError('فشل تحميل قائمة المستخدمين');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const handlePasswordReset = async (e) => {
        e.preventDefault();
        if (!selectedUser || !newPassword) return;

        setResetLoading(true);
        setError('');
        setSuccess('');

        try {
            const response = await apiClient.post(`/api/admin/users/${selectedUser.id}/reset-password`, {
                password: newPassword
            });

            if (response.data.success) {
                setSuccess(`تم تغيير كلمة مرور ${selectedUser.display_name} بنجاح`);
                setNewPassword('');
                setSelectedUser(null);
            }
        } catch (err) {
            setError(err.response?.data?.error || 'فشل تغيير كلمة المرور');
        } finally {
            setResetLoading(false);
        }
    };

    if (!isAdmin) {
        return (
            <div className="text-center py-12 text-red-600">
                <AlertCircle className="w-12 h-12 mx-auto mb-4" />
                <p>غير مصرح لك بالوصول لهذه الصفحة</p>
            </div>
        );
    }

    return (
        <div className="max-w-6xl mx-auto text-right" dir="rtl">
            <div className="mb-8 animate-fade-in-up">
                <h1 className="text-3xl font-black text-slate-800 mb-3">
                    <span className="gradient-text">لوحة تحكم المسؤول</span>
                </h1>
                <p className="text-slate-600">إدارة المستخدمين والصلاحيات</p>
            </div>

            {/* Status Messages */}
            {error && (
                <div className="p-4 mb-6 bg-red-50 text-red-700 rounded-xl flex items-center animate-fade-in-up">
                    <AlertCircle className="w-5 h-5 ml-2" />
                    {error}
                </div>
            )}
            {success && (
                <div className="p-4 mb-6 bg-green-50 text-green-700 rounded-xl flex items-center animate-fade-in-up">
                    <CheckCircle className="w-5 h-5 ml-2" />
                    {success}
                </div>
            )}

            <div className="grid lg:grid-cols-3 gap-6">
                {/* Users List */}
                <div className="lg:col-span-2">
                    <GlassCard className="p-6 animate-fade-in-up delay-100">
                        <div className="flex items-center justify-between mb-6">
                            <h2 className="text-xl font-bold flex items-center gap-2">
                                <Users className="w-5 h-5 text-primary-600" />
                                المستخدمين ({users.length})
                            </h2>
                            <button onClick={fetchUsers} className="p-2 hover:bg-slate-100 rounded-lg">
                                <RefreshCw className={`w-4 h-4 text-slate-500 ${loading ? 'animate-spin' : ''}`} />
                            </button>
                        </div>

                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="bg-slate-50 border-b border-slate-200">
                                        <th className="px-4 py-3 text-right font-medium text-slate-500">الاسم</th>
                                        <th className="px-4 py-3 text-right font-medium text-slate-500">البريد</th>
                                        <th className="px-4 py-3 text-center font-medium text-slate-500">الحالة</th>
                                        <th className="px-4 py-3 text-center font-medium text-slate-500">إجراءات</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100">
                                    {users.map(user => (
                                        <tr key={user.id} className="hover:bg-slate-50/50 transition-colors">
                                            <td className="px-4 py-3 font-medium text-slate-800">
                                                {user.display_name}
                                                {user.is_admin && (
                                                    <span className="mr-2 px-2 py-0.5 text-xs bg-purple-100 text-purple-700 rounded-full">
                                                        مسؤول
                                                    </span>
                                                )}
                                            </td>
                                            <td className="px-4 py-3 text-slate-600 font-mono text-xs">{user.email}</td>
                                            <td className="px-4 py-3 text-center">
                                                {user.is_active ? (
                                                    <span className="inline-block w-2.5 h-2.5 rounded-full bg-green-500" title="نشط"></span>
                                                ) : (
                                                    <span className="inline-block w-2.5 h-2.5 rounded-full bg-red-500" title="معطل"></span>
                                                )}
                                            </td>
                                            <td className="px-4 py-3 text-center">
                                                <button
                                                    onClick={() => {
                                                        setSelectedUser(user);
                                                        setSuccess('');
                                                        setError('');
                                                    }}
                                                    className="p-1.5 text-slate-500 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
                                                    title="تغيير كلمة المرور"
                                                >
                                                    <Lock className="w-4 h-4" />
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </GlassCard>
                </div>

                {/* Reset Password Panel */}
                <div>
                    <GlassCard className={`p-6 sticky top-24 transition-all duration-300 ${selectedUser ? 'translate-x-0 opacity-100' : 'translate-x-10 opacity-50 pointer-events-none'}`}>
                        <h3 className="font-bold text-lg mb-4 flex items-center gap-2 border-b border-slate-100 pb-3">
                            <Lock className="w-5 h-5 text-orange-500" />
                            تغيير كلمة المرور
                        </h3>

                        {selectedUser ? (
                            <form onSubmit={handlePasswordReset} className="space-y-4">
                                <div className="text-sm text-slate-600 mb-2">
                                    تغيير كلمة مرور: <span className="font-bold text-slate-800">{selectedUser.display_name}</span>
                                </div>

                                <div>
                                    <label className="text-xs font-medium text-slate-500 mb-1 block">كلمة المرور الجديدة</label>
                                    <input
                                        type="text"
                                        value={newPassword}
                                        onChange={(e) => setNewPassword(e.target.value)}
                                        className="w-full px-3 py-2 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500 text-left font-mono"
                                        placeholder="NewPassword123"
                                        required
                                        minLength={6}
                                        autoComplete="off"
                                    />
                                </div>

                                <div className="flex gap-2 pt-2">
                                    <GradientButton
                                        type="submit"
                                        className="flex-1 justify-center py-2 text-sm"
                                        isLoading={resetLoading}
                                    >
                                        حفظ التغيير
                                    </GradientButton>
                                    <button
                                        type="button"
                                        onClick={() => setSelectedUser(null)}
                                        className="px-4 py-2 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 text-sm"
                                    >
                                        إلغاء
                                    </button>
                                </div>
                            </form>
                        ) : (
                            <div className="text-center py-8 text-slate-400 text-sm">
                                حدد مستخدماً من القائمة لتغيير كلمة المرور
                            </div>
                        )}
                    </GlassCard>
                </div>
            </div>
        </div>
    );
};

export default AdminDashboard;
