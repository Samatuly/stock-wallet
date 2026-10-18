"use client";

import PositionForm from "@/components/PositionForm";
import type { NewPosition } from "@/lib/api";

export default function AddPositionForm({ onAdd }: { onAdd: (p: NewPosition) => Promise<void> }) {
  return (
    <>
      <PositionForm submitLabel="Добавить позицию" onSubmit={onAdd} />
    </>
  );
}
