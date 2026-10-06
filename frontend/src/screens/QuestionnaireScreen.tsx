import React from 'react';
import { useAnswerHistory, useQuestionnaire, useQuestionnaireActions, useSectionEstimate } from '@/hooks/useQuestionnaire';
import { interviewStep } from '@/api/questionnaire';
import { HttpError } from '@/api/client';
import { ErrorState, LoadingState } from '@/components/states';
import type { InterviewTurn, QuestionnaireQuestion, QuestionnaireSection } from '@/types/api';
import { formatEventDate } from '@/lib/dates';
import { Badge, Button, Page } from '@/ui';
import styles from './QuestionnaireScreen.module.css';

const STATUS_LABEL: Record<string, string> = {
  draft: 'Draft', added: 'Added', skipped: 'Skipped',
};

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'That did not work. Try again.';
}

/** A short conversation that ends with the owner's own words as the draft (ADR-0029). */
function Interview({ question, onDone, onCancel }: {
  question: QuestionnaireQuestion;
  onDone: (draft: string, transcript: InterviewTurn[]) => void;
  onCancel: () => void;
}) {
  const [turns, setTurns] = React.useState<InterviewTurn[]>([]);
  const [text, setText] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string>();
  const [done, setDone] = React.useState<{ draft: string; skipped: boolean }>();

  const step = React.useCallback(async (next: InterviewTurn[]) => {
    setBusy(true);
    setError(undefined);
    try {
      const reply = await interviewStep(question.id, next);
      const withReply = [...next, { role: 'iris' as const, text: reply.reply }];
      setTurns(withReply);
      if (reply.done) setDone({ draft: reply.draft, skipped: reply.skipped });
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }, [question.id]);

  const opened = React.useRef(false);
  React.useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    void step([]);
  }, [step]);

  const send = () => {
    const said = text.trim();
    if (!said) return;
    setText('');
    void step([...turns, { role: 'owner', text: said }]);
  };

  return (
    <div className={styles.interview} aria-label="Answering with IRIS">
      <p className={styles.muted}>
        Only this question and what you write here are sent to OpenAI, about a cent per question.
        IRIS never writes your answer: what you say becomes the draft.
      </p>
      <ol className={styles.turns}>
        {turns.map((turn, index) => (
          <li key={index} className={turn.role === 'iris' ? styles.iris : styles.owner}>
            <span className={styles.who}>{turn.role === 'iris' ? 'IRIS' : 'You'}</span>
            <p>{turn.text}</p>
          </li>
        ))}
      </ol>
      {busy && <p className={styles.muted} role="status">IRIS is thinking…</p>}
      {error && <p role="alert" className={styles.error}>{error}</p>}
      {done ? (
        <div className={styles.row}>
          {done.draft
            ? <Button variant="primary" onClick={() => onDone(done.draft, turns)}>Use my answer</Button>
            : <Button variant="primary" onClick={() => onDone('', turns)}>Skip this question</Button>}
          <Button variant="quiet" onClick={onCancel}>Close</Button>
        </div>
      ) : (
        <div className={styles.reply}>
          <textarea value={text} onChange={e => setText(e.target.value)} rows={3}
            aria-label="Your reply" placeholder="Answer in your own words, in English or Polish. Say “skip” to leave it."
            onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send(); }} />
          <div className={styles.row}>
            <Button variant="primary" disabled={busy || !text.trim()} onClick={send}>Send</Button>
            <Button variant="quiet" onClick={onCancel}>Cancel</Button>
          </div>
        </div>
      )}
    </div>
  );
}

function History({ id }: { id: string }) {
  const { data } = useAnswerHistory(id, true);
  if (!data) return null;
  return (
    <ul className={styles.history} aria-label="Earlier answers">
      {data.map(version => (
        <li key={version.version}>
          <span className={styles.muted}>
            {version.addedAt ? formatEventDate(version.addedAt.slice(0, 10)) : ''}
            {version.status === 'added' ? ', current' : ''}
          </span>
          <p>{version.answer}</p>
        </li>
      ))}
    </ul>
  );
}

function QuestionCard({ question }: { question: QuestionnaireQuestion }) {
  const actions = useQuestionnaireActions();
  const [text, setText] = React.useState(question.answer);
  const [polish, setPolish] = React.useState(false);
  const [interviewing, setInterviewing] = React.useState(false);
  const [history, setHistory] = React.useState(false);
  const [error, setError] = React.useState<string>();
  const saved = React.useRef(question.answer);

  React.useEffect(() => { setText(question.answer); saved.current = question.answer; }, [question.answer]);

  const save = (answer: string, source: 'form' | 'interview' = 'form', transcript?: InterviewTurn[]) => {
    if (answer.trim() === saved.current.trim() && source === 'form') return;
    saved.current = answer;
    actions.save.mutate({ id: question.id, answer, source, transcript },
      { onError: e => setError(message(e)), onSuccess: () => setError(undefined) });
  };

  // Drafts save themselves a moment after typing stops, and on leaving the box.
  React.useEffect(() => {
    if (text === saved.current) return;
    const timer = window.setTimeout(() => save(text), 1200);
    return () => window.clearTimeout(timer);
  }, [text]);

  const status = question.revising ? 'Revision' : STATUS_LABEL[question.status];
  return (
    <article className={styles.question} aria-labelledby={`q-${question.id}`}>
      <header className={styles.questionHead}>
        <span className={styles.number}>{question.number}</span>
        <h3 id={`q-${question.id}`} className={styles.questionText}>{question.text}</h3>
        {status && <Badge>{status}</Badge>}
      </header>
      {polish && <p className={styles.polish} lang="pl">{question.textPl}</p>}
      {question.status === 'skipped' ? (
        <p className={styles.muted}>You chose to leave this one.</p>
      ) : interviewing ? (
        <Interview question={question}
          onCancel={() => setInterviewing(false)}
          onDone={(draft, transcript) => {
            setInterviewing(false);
            if (draft) { setText(draft); save(draft, 'interview', transcript); }
            else actions.skip.mutate({ id: question.id, skipped: true });
          }} />
      ) : (
        <textarea className={styles.answer} value={text} rows={Math.min(12, Math.max(3, text.split('\n').length + 1))}
          aria-label={`Your answer to question ${question.number}`}
          onChange={e => setText(e.target.value)} onBlur={() => save(text)} />
      )}
      {error && <p role="alert" className={styles.error}>{error}</p>}
      <div className={styles.row}>
        <Button size="sm" variant="quiet" aria-pressed={polish} onClick={() => setPolish(open => !open)}>
          {polish ? 'Hide the Polish' : 'Show the Polish'}
        </Button>
        {question.status !== 'skipped' && !interviewing && (
          <Button size="sm" onClick={() => setInterviewing(true)}>Answer with IRIS</Button>
        )}
        <Button size="sm" variant="quiet"
          onClick={() => actions.skip.mutate({ id: question.id, skipped: question.status !== 'skipped' })}>
          {question.status === 'skipped' ? 'Answer after all' : 'Skip'}
        </Button>
        {question.history > 0 && (
          <Button size="sm" variant="quiet" aria-expanded={history} onClick={() => setHistory(open => !open)}>
            Earlier answers ({question.history})
          </Button>
        )}
      </div>
      {history && <History id={question.id} />}
    </article>
  );
}

function SectionFooter({ section }: { section: QuestionnaireSection }) {
  const actions = useQuestionnaireActions();
  const drafts = section.questions.filter(q => q.status === 'draft' && q.answer.trim()).length;
  const { data: estimate } = useSectionEstimate(section.id, drafts);
  const [done, setDone] = React.useState<number>();
  if (!drafts) {
    return done ? <p className={styles.muted} role="status">{done} answer{done === 1 ? '' : 's'} added. IRIS reads them in the background.</p> : null;
  }
  return (
    <footer className={styles.footer}>
      {estimate?.text && <p className={styles.cost}>{estimate.text}</p>}
      <p className={styles.muted}>Drafts stay on this machine until you add them.</p>
      <div className={styles.row}>
        <Button variant="primary" disabled={actions.add.isPending}
          onClick={() => actions.add.mutate(section.id, { onSuccess: result => setDone(result.added) })}>
          {actions.add.isPending ? 'Adding…' : `Add ${drafts} answer${drafts === 1 ? '' : 's'} to IRIS`}
        </Button>
      </div>
    </footer>
  );
}

export function QuestionnaireScreen() {
  const { data, isLoading, error, refetch } = useQuestionnaire();
  const [active, setActive] = React.useState<string>();
  const [polish, setPolish] = React.useState(false);

  if (isLoading) return <LoadingState label="Opening your questionnaire…" />;
  if (error instanceof HttpError && error.status === 404) {
    return (
      <Page title="Questionnaire">
        <p className={styles.muted}>The questionnaire is not on this machine yet. Its text is kept locally, outside the IRIS code.</p>
      </Page>
    );
  }
  if (error || !data) return <ErrorState onRetry={() => refetch()} />;

  const section = data.sections.find(s => s.id === active) ?? data.sections[0];
  return (
    <Page title="Questionnaire" width="standard"
      description="Your baseline questionnaire. Answer in your own words, in any order and over several sittings. Answers stay here as drafts until you add a section to IRIS.">
      <div className={styles.layout}>
        <nav aria-label="Sections" className={styles.sections}>
          {data.sections.map(s => {
            const answered = s.counts.added + s.counts.draft + s.counts.skipped;
            return (
              <button key={s.id} type="button" aria-current={s.id === section.id ? 'true' : undefined}
                className={`${styles.sectionButton} ${s.id === section.id ? styles.current : ''}`}
                onClick={() => setActive(s.id)}>
                <span>{s.title}</span>
                <span className={styles.progress}>{answered} of {s.counts.total}</span>
              </button>
            );
          })}
        </nav>
        <section className={styles.body} aria-labelledby="section-title">
          <header className={styles.sectionHead}>
            <h2 id="section-title" className={styles.sectionTitle}>{section.title}</h2>
            {(section.intro || section.introPl) && (
              <>
                <p className={styles.intro} lang={polish ? 'pl' : 'en'}>{polish ? section.introPl : section.intro}</p>
                <Button size="sm" variant="quiet" aria-pressed={polish} onClick={() => setPolish(open => !open)}>
                  {polish ? 'Read in English' : 'Read the Polish'}
                </Button>
              </>
            )}
          </header>
          <div className={styles.questions}>
            {section.questions.map(question => <QuestionCard key={question.id} question={question} />)}
          </div>
          <SectionFooter section={section} />
        </section>
      </div>
    </Page>
  );
}
