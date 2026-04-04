export function formatAgentLabel(agent: string): string {
  return agent.replaceAll("_", " ");
}

export function formatDatasetOption(option: string): string {
  if (option === "__auto_dataset__") {
    return "Auto-detect best match";
  }

  const parts = option.split(/[\\/]/);
  let name = parts.at(-1) ?? option;
  const group = parts.at(-2) ?? "data";

  if (name.length > 18) {
    name = name.substring(0, 15) + "...";
  }

  return `${name} (${group})`;
}

export function formatStatus(status: string | undefined): string {
  return (status ?? "unknown").replaceAll("_", " ");
}

export function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("Failed to read file"));
        return;
      }

      const [, payload = ""] = result.split(",", 2);
      resolve(payload);
    };
    reader.onerror = () => reject(reader.error ?? new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });
}
