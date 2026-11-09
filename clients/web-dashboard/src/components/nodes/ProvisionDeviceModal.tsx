"use client";

import React, { useState } from "react";
import { provisionDevice } from "@/lib/api/provisioning";
import { ApiClientError } from "@/lib/api/client";
import type { DeviceProvisionResponse } from "@/types/api";
import {
  MAC_REGEX,
  generateRandomKJoinHex,
  validateKJoinKey,
} from "@/lib/provisioning_utils";
import {
  ShieldCheck,
  X,
  Key,
  Copy,
  Check,
  Eye,
  EyeOff,
  Sparkles,
  AlertCircle,
  Cpu,
} from "lucide-react";

export interface ProvisionDeviceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (resp: DeviceProvisionResponse) => void;
}

export function ProvisionDeviceModal({
  isOpen,
  onClose,
  onSuccess,
}: ProvisionDeviceModalProps) {
  const [networkId, setNetworkId] = useState<string>("1");
  const [deviceMac, setDeviceMac] = useState<string>("");
  const [kJoin, setKJoin] = useState<string>("");
  const [generation, setGeneration] = useState<string>("1");
  const [showKey, setShowKey] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<boolean>(false);

  if (!isOpen) return null;

  const handleGenerateKey = () => {
    const randomHex = generateRandomKJoinHex();
    setKJoin(randomHex);
    setErrorMsg(null);
  };

  const handleCopyKey = async () => {
    if (!kJoin) return;
    try {
      await navigator.clipboard.writeText(kJoin);
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    } catch {
      // Fallback
    }
  };

  const handleClose = () => {
    if (isSubmitting) return;
    setErrorMsg(null);
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    const parsedNetworkId = parseInt(networkId, 10);
    if (isNaN(parsedNetworkId) || parsedNetworkId <= 0) {
      setErrorMsg("Network ID phải là số nguyên dương hợp lệ (>= 1).");
      return;
    }

    const cleanMac = deviceMac.trim().replace(/[:-]/g, "").toLowerCase();
    if (!MAC_REGEX.test(cleanMac)) {
      setErrorMsg("Device MAC phải gồm đúng 12 ký tự hex (ví dụ: aabbccddeeff).");
      return;
    }

    const cleanKJoin = kJoin.trim();
    if (!validateKJoinKey(cleanKJoin)) {
      setErrorMsg(
        "Khóa K_JOIN không hợp lệ. Vui lòng nhập 64 ký tự hex (32 bytes) hoặc Base64 32 bytes."
      );
      return;
    }

    const parsedGeneration = parseInt(generation, 10);
    if (isNaN(parsedGeneration) || parsedGeneration <= 0) {
      setErrorMsg("Generation phải là số nguyên dương (>= 1).");
      return;
    }

    setIsSubmitting(true);
    try {
      const resp = await provisionDevice({
        network_id: parsedNetworkId,
        device_mac: cleanMac,
        k_join: cleanKJoin,
        generation: parsedGeneration,
      });

      // Reset form on success
      setDeviceMac("");
      setKJoin("");
      setGeneration("1");
      setNetworkId("1");
      onSuccess(resp);
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        if (err.status === 409) {
          setErrorMsg(
            `Thiết bị [${cleanMac}] hoặc thế hệ khóa Generation ${parsedGeneration} đã tồn tại trong hệ thống (Conflict 409).`
          );
        } else if (err.status === 403) {
          setErrorMsg("Bạn không có quyền ADMIN để cấp phát thiết bị (Lỗi 403 Forbidden).");
        } else if (err.status === 400) {
          setErrorMsg(`Dữ liệu không hợp lệ (Lỗi 400): ${err.message}`);
        } else {
          setErrorMsg(`Lỗi từ máy chủ Backend (${err.status}): ${err.message}`);
        }
      } else if (err instanceof Error) {
        setErrorMsg(`Lỗi kết nối: ${err.message}`);
      } else {
        setErrorMsg("Đã xảy ra lỗi không xác định khi cấp phát thiết bị.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="provision-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm select-none"
    >
      <div className="w-full max-w-[540px] bg-surface rounded-xl shadow-none border border-border overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-canvas">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-500/10 text-interactive flex items-center justify-center">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <h3
                id="provision-modal-title"
                className="text-base font-semibold text-text-primary leading-tight"
              >
                Cấp phát thiết bị (Provision K_JOIN)
              </h3>
              <p className="text-xs text-text-secondary">
                Đăng ký định danh phần cứng và khóa gốc K_JOIN vào hệ thống
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            disabled={isSubmitting}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-surface transition-colors cursor-pointer disabled:opacity-50"
            aria-label="Đóng"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body / Form */}
        <form onSubmit={handleSubmit} className="p-6 flex flex-col gap-4 text-sm">
          {errorMsg && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-state-critical text-xs flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span className="leading-relaxed">{errorMsg}</span>
            </div>
          )}

          {/* Network ID */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="provision-network-id"
              className="text-xs font-medium text-text-primary flex items-center justify-between"
            >
              <span>
                Network ID <span className="text-state-critical">*</span>
              </span>
              <span className="text-[11px] text-text-secondary font-normal">
                Mặc định: 1
              </span>
            </label>
            <input
              id="provision-network-id"
              type="number"
              min="1"
              step="1"
              required
              value={networkId}
              onChange={(e) => setNetworkId(e.target.value)}
              placeholder="1"
              disabled={isSubmitting}
              className="w-full h-10 px-3 bg-surface text-text-primary border border-border rounded-lg text-sm focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive disabled:opacity-50"
            />
          </div>

          {/* Device MAC */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="provision-device-mac"
              className="text-xs font-medium text-text-primary flex items-center justify-between"
            >
              <span>
                Device MAC <span className="text-state-critical">*</span>
              </span>
              <span className="text-[11px] text-text-secondary font-normal font-mono">
                12 ký tự hex (6 bytes)
              </span>
            </label>
            <div className="relative flex items-center">
              <Cpu className="absolute left-3 w-4 h-4 text-text-secondary pointer-events-none" />
              <input
                id="provision-device-mac"
                type="text"
                maxLength={17}
                required
                value={deviceMac}
                onChange={(e) => setDeviceMac(e.target.value)}
                placeholder="aabbccddeeff"
                disabled={isSubmitting}
                className="w-full h-10 pl-9 pr-3 bg-surface text-text-primary border border-border rounded-lg text-sm font-mono lowercase focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive disabled:opacity-50 placeholder:font-sans placeholder:text-text-secondary/60"
              />
            </div>
            <p className="text-[11px] text-text-secondary">
              Định danh phần cứng duy nhất của node (hỗ trợ dạng aabbccddeeff hoặc aa:bb:cc:dd:ee:ff).
            </p>
          </div>

          {/* K_JOIN Key */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <label
                htmlFor="provision-k-join"
                className="text-xs font-medium text-text-primary"
              >
                Khóa K_JOIN (Root Key 32 bytes) <span className="text-state-critical">*</span>
              </label>
              <button
                type="button"
                onClick={handleGenerateKey}
                disabled={isSubmitting}
                className="inline-flex items-center gap-1 text-[11px] font-medium text-interactive hover:underline cursor-pointer disabled:opacity-50"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Tạo khóa ngẫu nhiên</span>
              </button>
            </div>
            <div className="relative flex items-center">
              <Key className="absolute left-3 w-4 h-4 text-text-secondary pointer-events-none" />
              <input
                id="provision-k-join"
                type={showKey ? "text" : "password"}
                required
                value={kJoin}
                onChange={(e) => setKJoin(e.target.value)}
                placeholder="Nhập hoặc tạo khóa bí mật 64 hex / 32-byte Base64"
                disabled={isSubmitting}
                className="w-full h-10 pl-9 pr-20 bg-surface text-text-primary border border-border rounded-lg text-xs font-mono focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive disabled:opacity-50 placeholder:font-sans placeholder:text-text-secondary/60"
              />
              <div className="absolute right-2 flex items-center gap-1">
                {kJoin && (
                  <button
                    type="button"
                    onClick={handleCopyKey}
                    title="Sao chép khóa"
                    className="w-7 h-7 flex items-center justify-center text-text-secondary hover:text-text-primary transition-colors rounded cursor-pointer"
                  >
                    {copiedKey ? (
                      <Check className="w-3.5 h-3.5 text-state-connected" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  aria-label={showKey ? "Ẩn khóa" : "Hiện khóa"}
                  className="w-7 h-7 flex items-center justify-center text-text-secondary hover:text-text-primary transition-colors rounded cursor-pointer"
                >
                  {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>
            </div>
            <p className="text-[11px] text-text-secondary">
              Khóa AES-256 đối xứng dùng trong giao thức Join v2. Chuỗi 64 ký tự hex (32 bytes) hoặc Base64.
            </p>
          </div>

          {/* Generation */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="provision-generation"
              className="text-xs font-medium text-text-primary flex items-center justify-between"
            >
              <span>
                Generation <span className="text-state-critical">*</span>
              </span>
              <span className="text-[11px] text-text-secondary font-normal">
                Mặc định: 1
              </span>
            </label>
            <input
              id="provision-generation"
              type="number"
              min="1"
              step="1"
              required
              value={generation}
              onChange={(e) => setGeneration(e.target.value)}
              placeholder="1"
              disabled={isSubmitting}
              className="w-full h-10 px-3 bg-surface text-text-primary border border-border rounded-lg text-sm focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive disabled:opacity-50"
            />
          </div>

          {/* Modal Footer Buttons */}
          <div className="mt-2 pt-4 border-t border-border flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={handleClose}
              disabled={isSubmitting}
              className="h-10 px-4 rounded-lg border border-border bg-surface hover:bg-canvas text-text-primary text-xs font-medium transition-colors cursor-pointer disabled:opacity-50"
            >
              Hủy bỏ
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="h-10 px-4 rounded-lg bg-interactive hover:bg-interactive-hover disabled:opacity-50 text-white text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer shadow-none"
            >
              {isSubmitting ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Đang cấp phát...</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="w-4 h-4" />
                  <span>Xác nhận cấp phát</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
