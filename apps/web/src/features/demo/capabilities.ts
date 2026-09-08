import { api } from "../../api/client";
import { SafeApiError } from "../shared/apiError";

export async function getDemoCapabilities(signal?: AbortSignal) {
  const result = await api.GET("/api/v1/demo/capabilities", { signal });
  if (!result.data) throw new SafeApiError("Không thể kiểm tra chế độ demo.");
  return result.data;
}
