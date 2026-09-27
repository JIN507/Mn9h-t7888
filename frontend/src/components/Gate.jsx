/* The front door. Letters of تحقق drift across the screen; typing the
   username stills them, typing the password gathers them into the word
   above the form, and a correct login fades everything away into the app. */
import { useEffect, useMemo, useRef, useState, createContext, useContext } from 'react';
import { ArrowLeft } from 'lucide-react';
import apiClient from '../services/apiClient';

const GateContext = createContext({ username: null, logout: () => {} });
export const useGate = () => useContext(GateContext);

const LETTERS = ['ت', 'ح', 'ق', 'ق'];
const COUNT = 28;                               // floating glyphs on screen

/* deterministic pseudo-random so the field looks the same across re-renders */
const rand = (seed) => { const x = Math.sin(seed * 9301 + 49297) * 233280; return x - Math.floor(x); };

const makeGlyphs = () => Array.from({ length: COUNT }, (_, i) => ({
    id: i,
    ch: LETTERS[i % 4],
    slot: i % 4,                                // which letter of the word it becomes
    x: rand(i + 1) * 100,                       // vw
    y: rand(i + 11) * 100,                      // vh
    size: 26 + rand(i + 21) * 54,               // px
    dur: 14 + rand(i + 31) * 18,                // s
    delay: -rand(i + 41) * 30,                  // s (start mid-flight)
    drift: 30 + rand(i + 51) * 60,              // px
    op: 0.10 + rand(i + 61) * 0.22,
}));

export function GateScreen({ onEnter }) {
    const glyphs = useMemo(makeGlyphs, []);
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState(null);
    const [busy, setBusy] = useState(false);
    const [phase, setPhase] = useState('drift');   // drift | still | gather | leave
    const formRef = useRef(null);
    const [anchor, setAnchor] = useState({ x: 0, y: 0 });

    // phases follow the typing
    useEffect(() => {
        if (phase === 'leave') return;
        if (password.length > 0) setPhase('gather');
        else if (username.length > 0) setPhase('still');
        else setPhase('drift');
    }, [username, password, phase]);

    // where the word gathers: centred above the form
    useEffect(() => {
        const place = () => {
            const r = formRef.current?.getBoundingClientRect();
            if (r) setAnchor({ x: r.left + r.width / 2, y: r.top - 72 });
        };
        place();
        window.addEventListener('resize', place);
        return () => window.removeEventListener('resize', place);
    }, []);

    const submit = async (e) => {
        e.preventDefault();
        if (busy) return;
        setBusy(true); setError(null);
        try {
            await apiClient.post('/api/gate/login', { username: username.trim(), password });
            setPhase('leave');
            setTimeout(() => onEnter(username.trim()), 1400);
        } catch (err) {
            setError(err.response?.data?.error || 'تعذّر الاتصال بالخادم');
            setBusy(false);
        }
    };

    // target positions for the gathered word (RTL: ت on the right)
    const spacing = 38;
    const target = (slot) => ({ x: anchor.x + (1.5 - slot) * spacing, y: anchor.y });
    const gathered = phase === 'gather' || phase === 'leave';

    return (
        <div className={`gate ${phase}`} dir="rtl">
            <div className="gate-bg" />
            {glyphs.map((g) => {
                // one glyph per letter of the word gathers; the rest fade out
                const leads = g.id < 4;
                const t = target(g.slot);
                const style = gathered && leads
                    ? { left: t.x, top: t.y, fontSize: 64, opacity: 1, transform: 'translate(-50%, -50%)', animationPlayState: 'paused' }
                    : {
                        left: `${g.x}vw`, top: `${g.y}vh`, fontSize: g.size, opacity: gathered ? 0 : g.op,
                        '--drift': `${g.drift}px`, animationDuration: `${g.dur}s`, animationDelay: `${g.delay}s`,
                        animationPlayState: phase === 'drift' ? 'running' : 'paused',
                    };
                return <span key={g.id} className={`gate-glyph ${leads ? 'lead' : ''}`} style={style}>{g.ch}</span>;
            })}

            {/* the connected word the letters become */}
            <span className="gate-gathered" style={{ left: anchor.x, top: anchor.y }}>تحقق</span>

            <form ref={formRef} onSubmit={submit} className="gate-card" autoComplete="off">
                <div className="gate-title">
                    <span className="gate-word">تحقق</span>
                    <p>منصة التحقق من الوسائط</p>
                </div>
                <label className="gate-field">
                    <span>اسم المستخدم</span>
                    <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus spellCheck={false} dir="ltr" />
                </label>
                <label className="gate-field">
                    <span>كلمة المرور</span>
                    <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} dir="ltr" />
                </label>
                {error && <p className="gate-error">{error}</p>}
                <button type="submit" className="gate-btn" disabled={busy || !username || !password}>
                    {busy ? 'جارٍ الدخول…' : <>دخول <ArrowLeft className="w-4 h-4" /></>}
                </button>
            </form>
        </div>
    );
}

export function GateProvider({ children }) {
    const [state, setState] = useState({ checked: false, username: null });
    useEffect(() => {
        apiClient.get('/api/gate/me')
            .then((r) => setState({ checked: true, username: r.data?.username || 'open' }))
            .catch(() => setState({ checked: true, username: null }));
    }, []);
    const logout = async () => {
        try { await apiClient.post('/api/gate/logout'); } catch { /* ignore */ }
        setState({ checked: true, username: null });
    };
    if (!state.checked) return <div className="gate-boot" />;
    if (!state.username) return <GateScreen onEnter={(u) => setState({ checked: true, username: u })} />;
    return (
        <GateContext.Provider value={{ username: state.username, logout }}>
            <div className="gate-enter">{children}</div>
        </GateContext.Provider>
    );
}
