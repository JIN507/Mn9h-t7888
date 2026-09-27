/* The front door.
   Large, faint letters of تحقق drift slowly across the screen. Nothing reacts
   to typing. When the credentials are accepted, four letters fly together
   above the form and become the word, the word swells and dissolves, and the
   app appears underneath. */
import { useEffect, useMemo, useRef, useState, createContext, useContext } from 'react';
import apiClient from '../services/apiClient';

const GateContext = createContext({ username: null, logout: () => {} });
export const useGate = () => useContext(GateContext);

const LETTERS = ['ت', 'ح', 'ق', 'ق'];
const COUNT = 18;

const rand = (seed) => { const x = Math.sin(seed * 9301 + 49297) * 233280; return x - Math.floor(x); };

const makeGlyphs = () => Array.from({ length: COUNT }, (_, i) => {
    const depth = rand(i + 7);                          // 0 far … 1 near
    return {
        id: i,
        ch: LETTERS[i % 4],
        slot: i % 4,
        x: 4 + rand(i + 1) * 92,                       // vw
        y: 4 + rand(i + 11) * 92,                      // vh
        size: 48 + depth * 150,                        // px
        blur: (1 - depth) * 3,                         // px, far letters are softer
        op: 0.05 + depth * 0.10,
        dur: 28 + rand(i + 31) * 26,                   // s, slow
        delay: -rand(i + 41) * 40,
        dx: (rand(i + 51) - 0.5) * 220,                // px drift
        dy: (rand(i + 61) - 0.5) * 160,
        rot: (rand(i + 71) - 0.5) * 10,
    };
});

export function GateScreen({ onEnter }) {
    const glyphs = useMemo(makeGlyphs, []);
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState(null);
    const [busy, setBusy] = useState(false);
    const [phase, setPhase] = useState('idle');       // idle | gather | word | open
    const formRef = useRef(null);
    const [anchor, setAnchor] = useState({ x: 0, y: 0 });

    useEffect(() => {
        const place = () => {
            const r = formRef.current?.getBoundingClientRect();
            if (r) setAnchor({ x: r.left + r.width / 2, y: r.top - 90 });
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
            // the sequence: letters fly in (1.3 s) -> the word (0.9 s) -> the word opens the app (1.4 s)
            setPhase('gather');
            setTimeout(() => setPhase('word'), 1300);
            setTimeout(() => setPhase('open'), 2200);
            setTimeout(() => onEnter(username.trim()), 3500);
        } catch (err) {
            setError(err.response?.data?.error || 'تعذّر الاتصال بالخادم');
            setBusy(false);
            setPhase('shake');
            setTimeout(() => setPhase('idle'), 500);
        }
    };

    const spacing = 46;
    const target = (slot) => ({ x: anchor.x + (1.5 - slot) * spacing, y: anchor.y });
    const flying = phase === 'gather' || phase === 'word' || phase === 'open';

    return (
        <div className={`gate ${phase}`} dir="rtl">
            <div className="gate-bg" />
            {glyphs.map((g) => {
                const lead = g.id < 4;
                const t = target(g.slot);
                const style = flying && lead
                    ? { left: t.x, top: t.y, fontSize: 84, opacity: phase === 'gather' ? 1 : 0, filter: 'none',
                        transform: 'translate(-50%, -50%)', animation: 'none' }
                    : { left: `${g.x}vw`, top: `${g.y}vh`, fontSize: g.size, opacity: flying ? 0 : g.op,
                        filter: `blur(${g.blur}px)`, animationDuration: `${g.dur}s`, animationDelay: `${g.delay}s`,
                        '--dx': `${g.dx}px`, '--dy': `${g.dy}px`, '--rot': `${g.rot}deg` };
                return <span key={g.id} className="gate-glyph" style={style}>{g.ch}</span>;
            })}

            <span className="gate-word-final" style={{ left: anchor.x, top: anchor.y }}>تحقق</span>

            <form ref={formRef} onSubmit={submit} className="gate-card" autoComplete="off">
                <div className="gate-brand">تحقق</div>
                <p className="gate-sub">منصة التحقق من الوسائط</p>
                <div className="gate-field">
                    <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder=" " autoFocus spellCheck={false} dir="ltr" id="gate-user" />
                    <label htmlFor="gate-user">اسم المستخدم</label>
                </div>
                <div className="gate-field">
                    <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder=" " dir="ltr" id="gate-pass" />
                    <label htmlFor="gate-pass">كلمة المرور</label>
                </div>
                {error && <p className="gate-error">{error}</p>}
                <button type="submit" className="gate-btn" disabled={busy || !username || !password}>
                    {busy ? 'جارٍ التحقق…' : 'دخول'}
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
