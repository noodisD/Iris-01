import { Link, useParams, useSearchParams } from 'react-router-dom';
import { SystemView } from '@/components/observatory/SystemView';
import {
  AnalysisTab, ClientsTab, DatabaseTab, ErrorsTab, LiveTab, LlmTab, OperationsTab, OverviewTab,
  QueueTab, TraceView, TracesTab,
} from '@/components/observatory/tabs';
import { Button, Page, TabPanel, Tabs } from '@/ui';

const TABS = [
  { value: 'overview', label: 'Overview' },
  { value: 'system', label: 'System' },
  { value: 'live', label: 'Live' },
  { value: 'traces', label: 'Traces' },
  { value: 'operations', label: 'Operations' },
  { value: 'queue', label: 'Queue' },
  { value: 'database', label: 'Database' },
  { value: 'llm', label: 'LLM' },
  { value: 'analysis', label: 'Analysis' },
  { value: 'errors', label: 'Errors' },
  { value: 'clients', label: 'Clients' },
] as const;

type View = typeof TABS[number]['value'];

export function ObservatoryScreen() {
  const { traceId } = useParams();
  const [params, setParams] = useSearchParams();
  const view = (params.get('view') || 'overview') as View;
  const systemView = !traceId && view === 'system';
  return (
    <Page title="Observatory" width="wide" workspace={systemView} description={systemView ? undefined : 'What IRIS is doing right now, and where time and failures go.'}>
      {traceId ? (
        <>
          <Button><Link to="/observatory">← All traces</Link></Button>
          <TraceView traceId={traceId} />
        </>
      ) : (
        <Tabs label="Observatory" value={view} tabs={[...TABS]} fill={view === 'system'} onChange={next => setParams(current => { current.set('view', next); return current; })}>
          <TabPanel value="overview"><OverviewTab /></TabPanel>
          <TabPanel value="system"><SystemView /></TabPanel>
          <TabPanel value="live"><LiveTab /></TabPanel>
          <TabPanel value="traces"><TracesTab /></TabPanel>
          <TabPanel value="operations"><OperationsTab /></TabPanel>
          <TabPanel value="queue"><QueueTab /></TabPanel>
          <TabPanel value="database"><DatabaseTab /></TabPanel>
          <TabPanel value="llm"><LlmTab /></TabPanel>
          <TabPanel value="analysis"><AnalysisTab /></TabPanel>
          <TabPanel value="errors"><ErrorsTab /></TabPanel>
          <TabPanel value="clients"><ClientsTab /></TabPanel>
        </Tabs>
      )}
    </Page>
  );
}
