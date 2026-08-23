export type Evidence = {
  id: string;
  manuscript_version_id?: string;
  chapter_id?: string;
  chapter?: string;
  scene?: string;
  paragraph_id?: string;
  text: string;
  start_offset?: number;
  end_offset?: number;
  claim?: string;
};

export type UiContext =
  | { type: "project" }
  | { type: "chapter"; chapter_id: string }
  | { type: "character"; entity_id: string }
  | { type: "issue"; issue_id: string };

export type Dictionary = Record<string, unknown>;
