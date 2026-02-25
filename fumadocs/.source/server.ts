// @ts-nocheck
import { default as __fd_glob_25 } from "../content/docs/scenarios/meta.json?collection=meta"
import { default as __fd_glob_24 } from "../content/docs/reference/meta.json?collection=meta"
import { default as __fd_glob_23 } from "../content/docs/guides/meta.json?collection=meta"
import { default as __fd_glob_22 } from "../content/docs/api-reference/meta.json?collection=meta"
import { default as __fd_glob_21 } from "../content/docs/meta.json?collection=meta"
import * as __fd_glob_20 from "../content/docs/scenarios/scenario-e.mdx?collection=docs"
import * as __fd_glob_19 from "../content/docs/scenarios/scenario-d.mdx?collection=docs"
import * as __fd_glob_18 from "../content/docs/scenarios/scenario-c.mdx?collection=docs"
import * as __fd_glob_17 from "../content/docs/scenarios/scenario-b.mdx?collection=docs"
import * as __fd_glob_16 from "../content/docs/scenarios/scenario-a.mdx?collection=docs"
import * as __fd_glob_15 from "../content/docs/reference/error-codes.mdx?collection=docs"
import * as __fd_glob_14 from "../content/docs/reference/business-rules.mdx?collection=docs"
import * as __fd_glob_13 from "../content/docs/guides/validation-pipeline.mdx?collection=docs"
import * as __fd_glob_12 from "../content/docs/guides/how-refunds-work.mdx?collection=docs"
import * as __fd_glob_11 from "../content/docs/guides/financial-precision.mdx?collection=docs"
import * as __fd_glob_10 from "../content/docs/guides/calculation-engine.mdx?collection=docs"
import * as __fd_glob_9 from "../content/docs/api-reference/query-audit.mdx?collection=docs"
import * as __fd_glob_8 from "../content/docs/api-reference/list-transactions.mdx?collection=docs"
import * as __fd_glob_7 from "../content/docs/api-reference/list-refunds.mdx?collection=docs"
import * as __fd_glob_6 from "../content/docs/api-reference/introduction.mdx?collection=docs"
import * as __fd_glob_5 from "../content/docs/api-reference/get-transaction.mdx?collection=docs"
import * as __fd_glob_4 from "../content/docs/api-reference/get-refund.mdx?collection=docs"
import * as __fd_glob_3 from "../content/docs/api-reference/create-refund.mdx?collection=docs"
import * as __fd_glob_2 from "../content/docs/quickstart.mdx?collection=docs"
import * as __fd_glob_1 from "../content/docs/introduction.mdx?collection=docs"
import * as __fd_glob_0 from "../content/docs/authentication.mdx?collection=docs"
import { server } from 'fumadocs-mdx/runtime/server';
import type * as Config from '../source.config';

const create = server<typeof Config, import("fumadocs-mdx/runtime/types").InternalTypeConfig & {
  DocData: {
  }
}>({"doc":{"passthroughs":["extractedReferences"]}});

export const docs = await create.doc("docs", "content/docs", {"authentication.mdx": __fd_glob_0, "introduction.mdx": __fd_glob_1, "quickstart.mdx": __fd_glob_2, "api-reference/create-refund.mdx": __fd_glob_3, "api-reference/get-refund.mdx": __fd_glob_4, "api-reference/get-transaction.mdx": __fd_glob_5, "api-reference/introduction.mdx": __fd_glob_6, "api-reference/list-refunds.mdx": __fd_glob_7, "api-reference/list-transactions.mdx": __fd_glob_8, "api-reference/query-audit.mdx": __fd_glob_9, "guides/calculation-engine.mdx": __fd_glob_10, "guides/financial-precision.mdx": __fd_glob_11, "guides/how-refunds-work.mdx": __fd_glob_12, "guides/validation-pipeline.mdx": __fd_glob_13, "reference/business-rules.mdx": __fd_glob_14, "reference/error-codes.mdx": __fd_glob_15, "scenarios/scenario-a.mdx": __fd_glob_16, "scenarios/scenario-b.mdx": __fd_glob_17, "scenarios/scenario-c.mdx": __fd_glob_18, "scenarios/scenario-d.mdx": __fd_glob_19, "scenarios/scenario-e.mdx": __fd_glob_20, });

export const meta = await create.meta("meta", "content/docs", {"meta.json": __fd_glob_21, "api-reference/meta.json": __fd_glob_22, "guides/meta.json": __fd_glob_23, "reference/meta.json": __fd_glob_24, "scenarios/meta.json": __fd_glob_25, });