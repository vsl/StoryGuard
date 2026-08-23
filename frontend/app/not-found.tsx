import { ButtonLink, Card, EmptyState } from "@/components/ui";

export default function NotFound() {
  return (
    <main className="mx-auto grid min-h-screen max-w-xl place-items-center p-6">
      <Card className="w-full">
        <EmptyState
          title="Page not found"
          description="This StoryGuard page does not exist or is no longer available."
          action={<ButtonLink href="/projects">Back to stories</ButtonLink>}
        />
      </Card>
    </main>
  );
}
