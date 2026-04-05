import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import GlassCard from '../components/GlassCard';
import GradientButton from '../components/GradientButton';
import { LogIn, Mail, Lock, AlertCircle } from 'lucide-react';

const Login = () => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const { login } = useAuth();
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            await login(email, password);
            navigate('/');
        } catch (err) {
            setError(err.response?.data?.error || 'فشل تسجيل الدخول');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-[80vh] flex items-center justify-center px-4">
            <GlassCard className="w-full max-w-md p-8 animate-fade-in-up">
                <div className="text-center mb-8">
                    <div className="w-16 h-16 bg-primary-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                        <LogIn className="w-8 h-8 text-primary-600" />
                    </div>
                    <h1 className="text-2xl font-bold text-slate-800">تسجيل الدخول</h1>
                    <p className="text-slate-500 mt-2">مرحباً بك مجدداً في منصة تحقق</p>
                </div>

                {error && (
                    <div className="mb-6 p-3 bg-red-50 text-red-600 rounded-xl flex items-center gap-2 text-sm">
                        <AlertCircle className="w-4 h-4 flex-shrink-0" />
                        {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="space-y-1 text-right">
                        <label className="text-sm font-medium text-slate-700">البريد الإلكتروني</label>
                        <div className="relative">
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full px-4 py-2 pr-10 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500 text-right"
                                placeholder="name@example.com"
                                dir="ltr"
                                required
                            />
                            <Mail className="w-5 h-5 text-slate-400 absolute right-3 top-2.5" />
                        </div>
                    </div>

                    <div className="space-y-1 text-right">
                        <label className="text-sm font-medium text-slate-700">كلمة المرور</label>
                        <div className="relative">
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="w-full px-4 py-2 pr-10 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500 text-right"
                                placeholder="••••••••"
                                dir="ltr"
                                required
                            />
                            <Lock className="w-5 h-5 text-slate-400 absolute right-3 top-2.5" />
                        </div>
                    </div>

                    <div className="pt-2">
                        <GradientButton
                            type="submit"
                            icon={LogIn}
                            className="w-full justify-center"
                            isLoading={loading}
                        >
                            تسجيل الدخول
                        </GradientButton>
                    </div>
                </form>

                <div className="mt-6 text-center text-sm text-slate-500">
                    ليس لديك حساب؟{' '}
                    <Link to="/register" className="text-primary-600 font-medium hover:text-primary-700">
                        إنشاء حساب جديد
                    </Link>
                </div>
            </GlassCard>
        </div>
    );
};

export default Login;
