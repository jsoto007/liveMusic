import { GENRES, type Genre } from "@live-msc/shared";

export function GenreChips({
  selected,
  onToggle,
}: {
  selected: Genre[];
  onToggle: (genre: Genre) => void;
}) {
  return (
    <div className="chip-row" role="group" aria-label="Filter by genre">
      {GENRES.map((genre) => {
        const on = selected.includes(genre.value);
        return (
          <button
            key={genre.value}
            type="button"
            className="chip"
            // aria-pressed carries the state to assistive tech AND drives the
            // selected styling, so the two can never disagree.
            aria-pressed={on}
            onClick={() => onToggle(genre.value)}
          >
            {genre.label}
          </button>
        );
      })}
    </div>
  );
}
