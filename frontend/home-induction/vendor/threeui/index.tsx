import { InductionButton, type NeuformIsolatedEffectProps } from "./src/shaders/neuform-isolated/NeuformIsolatedEffects";
export function ShaderButtons({variant, ...props}: NeuformIsolatedEffectProps & {variant: "induction-button"}) {
  if (variant !== "induction-button") throw new Error("Unregistered button variant");
  return <InductionButton {...props} />;
}
