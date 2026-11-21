/** Content collection (no CMS until scale demands it — architecture §10). */

export interface Article {
  slug: string;
  section: "blog" | "guides" | "compare";
  title: string;
  description: string;
  body: Array<{ heading?: string; paragraphs: string[] }>;
}

export const ARTICLES: Article[] = [
  {
    slug: "how-to-convert-math-pdf-to-editable-word",
    section: "blog",
    title: "How to convert a math PDF to editable Word without retyping",
    description:
      "The practical workflow: pick the right pages, convert with Standard, and check the equations that matter before you trust the file.",
    body: [
      {
        heading: "Convert only what you need",
        paragraphs: [
          "Most documents are converted once and edited for weeks. Converting the ten pages you will actually change beats converting two hundred you will not touch.",
          "Start with a single representative page: one with a fraction, one table, one figure. If that page converts well, the rest of the document usually follows.",
        ],
      },
      {
        heading: "Check three things before trusting the file",
        paragraphs: [
          "First, click three equations and edit a character in each. Second, confirm every figure is present and captioned. Third, scroll the whole document once for reading order — especially in two-column papers.",
          "Verified mode is coming soon. Today, Standard conversion keeps every equation editable, so you can spot-check the ones that matter yourself.",
        ],
      },
    ],
  },
  {
    slug: "why-generic-pdf-conversion-breaks-equations",
    section: "blog",
    title: "Why generic PDF converters destroy equations",
    description:
      "Fractions become shuffled text, bounds detach, matrices collapse. The failure modes are structural — which is why they need a math-first converter.",
    body: [
      {
        heading: "PDFs store position, not meaning",
        paragraphs: [
          "A PDF places glyphs at coordinates. A fraction bar is a line; the numerator is text floating above it. Generic converters read the characters in position order and emit 'x 2 + 1 x − 1' — every symbol present, all meaning gone.",
          "Superscripts and subscripts suffer the same fate: without baseline analysis, x² becomes x2 and the mathematics silently changes.",
        ],
      },
      {
        heading: "Structure must be rebuilt, not extracted",
        paragraphs: [
          "A math-first converter detects mathematical regions, recognizes their structure into an intermediate representation, and renders native Word equations from that structure. Text extraction alone can never do this — the structure was never in the file to begin with.",
        ],
      },
    ],
  },
  {
    slug: "teacher-workflow-editable-worksheets",
    section: "guides",
    title: "Teacher workflow: turn a PDF chapter into next week's worksheet",
    description:
      "A repeatable 15-minute workflow for converting textbook material into editable, remixable Word worksheets.",
    body: [
      {
        heading: "1. Convert the chapter section",
        paragraphs: [
          "Upload the chapter PDF and convert the page range you teach from. Keep the source file — you will reuse it every term.",
        ],
      },
      {
        heading: "2. Remix, don't rebuild",
        paragraphs: [
          "Change the numbers in each problem (the equations are editable, so this takes seconds), delete the questions you are skipping, and duplicate the file for version B of the test.",
        ],
      },
      {
        heading: "3. Keep a template",
        paragraphs: [
          "Save your fonts, header, and answer-key formatting as a Word template. Paste converted problems into it and every worksheet looks like yours.",
        ],
      },
    ],
  },
  {
    slug: "researcher-workflow-papers-to-manuscripts",
    section: "guides",
    title: "Researcher workflow: from legacy PDFs to editable manuscripts",
    description:
      "How to convert equation-heavy papers and theses into Word you can revise, with equation numbers and references intact.",
    body: [
      {
        heading: "Preserve the numbering first",
        paragraphs: [
          "Numbered equations are the skeleton of a technical manuscript. Verify that each (n) sits with its equation before editing anything else — renumbering by hand afterward is where errors creep in.",
        ],
      },
      {
        heading: "Tables and figures travel together",
        paragraphs: [
          "Convert with figures preserved in place, then replace legacy low-resolution figures with fresh exports. The captions and cross-references stay valid because the structure survived.",
        ],
      },
    ],
  },
];

export function articlesBySection(section: Article["section"]): Article[] {
  return ARTICLES.filter((a) => a.section === section);
}

export function findArticle(section: string, slug: string): Article | undefined {
  return ARTICLES.find((a) => a.section === section && a.slug === slug);
}
