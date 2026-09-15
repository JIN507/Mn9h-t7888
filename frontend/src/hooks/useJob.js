import { useEffect, useState } from 'react';

/**
 * Follow a background job via SSE (/api/jobs/<id>/events).
 *
 * The server ends each stream after ~25s (worker protection); EventSource
 * reconnects automatically until a result/job_error event arrives.
 *
 * Returns { status: idle|running|done|error, progress: string[], result, error }
 * where `result` is { status: <http code>, payload: <legacy response body> }.
 */
export default function useJob(jobId) {
    const [progress, setProgress] = useState([]);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [status, setStatus] = useState('idle');

    useEffect(() => {
        if (!jobId) {
            setStatus('idle');
            return undefined;
        }
        setProgress([]);
        setResult(null);
        setError(null);
        setStatus('running');

        const es = new EventSource(`/api/jobs/${jobId}/events`);
        es.addEventListener('progress', (e) => {
            try {
                const d = JSON.parse(e.data);
                setProgress((p) => [...p, d.message]);
            } catch { /* ignore malformed event */ }
        });
        es.addEventListener('result', (e) => {
            try {
                setResult(JSON.parse(e.data));
                setStatus('done');
            } catch {
                setError('استجابة غير صالحة من الخادم');
                setStatus('error');
            }
            es.close();
        });
        es.addEventListener('job_error', (e) => {
            let message = 'فشل تنفيذ المهمة';
            try { message = JSON.parse(e.data).error || message; } catch { /* noop */ }
            setError(message);
            setStatus('error');
            es.close();
        });
        // 'keepalive' events end the stream on purpose — EventSource reconnects.
        // But if the job itself is gone (server restarted, job expired) the
        // stream 404s forever: check the job once per reconnect and bail.
        es.onerror = async () => {
            try {
                const r = await fetch(`/api/jobs/${jobId}`);
                if (r.status === 404) {
                    setError('انتهت المهمة على الخادم دون نتيجة (أُعيد تشغيل الخادم؟) — أعد المحاولة');
                    setStatus('error');
                    es.close();
                }
            } catch { /* network blip — let EventSource retry */ }
        };
        const deadline = setTimeout(() => {
            setError('استغرقت المهمة وقتاً أطول من المتوقع — أعد المحاولة');
            setStatus('error');
            es.close();
        }, 6 * 60 * 1000);

        return () => { clearTimeout(deadline); es.close(); };
    }, [jobId]);

    return { status, progress, result, error };
}
