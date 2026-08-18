/** Star ratings — printed small, and a tappable input for writing one. */

import { Pressable, View } from "react-native";
import { Star } from "lucide-react-native";

import { colors, ink } from "../lib/theme";

const STEPS = [1, 2, 3, 4, 5] as const;

export function Stars({ rating, size = 13 }: { rating: number; size?: number }) {
  return (
    <View
      style={{ flexDirection: "row", gap: 2 }}
      accessible
      accessibilityLabel={`${rating} of 5 stars`}
    >
      {STEPS.map((step) => (
        <Star
          key={step}
          size={size}
          strokeWidth={1.4}
          color={step <= rating ? colors.accent : ink.ghost}
          fill={step <= rating ? colors.accent : "transparent"}
        />
      ))}
    </View>
  );
}

export function StarInput({
  value,
  onChange,
  size = 24,
}: {
  value: number;
  onChange: (next: number) => void;
  size?: number;
}) {
  return (
    <View style={{ flexDirection: "row", gap: 8 }} accessibilityRole="radiogroup">
      {STEPS.map((step) => (
        <Pressable
          key={step}
          onPress={() => onChange(step)}
          hitSlop={6}
          accessibilityRole="radio"
          accessibilityState={{ selected: step <= value }}
          accessibilityLabel={step === 1 ? "1 star" : `${step} stars`}
        >
          <Star
            size={size}
            strokeWidth={1.4}
            color={step <= value ? colors.accent : ink.ghost}
            fill={step <= value ? colors.accent : "transparent"}
          />
        </Pressable>
      ))}
    </View>
  );
}
