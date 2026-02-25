import { createOpenAPI } from 'fumadocs-openapi/server';
import { createAPIPage } from 'fumadocs-openapi/ui';
import spec from '../../public/openapi.json';

const openapi = createOpenAPI({
  input: () => ({ spec: spec as never }),
});
const APIPage = createAPIPage(openapi);

export default async function APIReferencePage() {
  const document = await openapi.getSchema('spec');
  return (
    <main className="container mx-auto py-8">
      <APIPage
        document={document}
        operations={[
          { path: '/api/v1/refunds', method: 'post' },
          { path: '/api/v1/refunds', method: 'get' },
          { path: '/api/v1/refunds/{refund_id}', method: 'get' },
          { path: '/api/v1/transactions', method: 'get' },
          { path: '/api/v1/transactions/{transaction_id}', method: 'get' },
          { path: '/api/v1/audit', method: 'get' },
        ]}
      />
    </main>
  );
}
