/**
 * SyBlog Virtual OS — CPU Software Implementation Bridge
 * v86 에뮬레이터에 CPU 소프트웨어 설정을 주입하는 브릿지 모듈
 * CPU 종류: 30종 (Intel/AMD/레거시/서버/가상/레트로)
 */
'use strict';

(function (global) {

  /**
   * v86 에뮬레이터에 CPU 설정 주입
   * CPU_DB는 virtual_os_emulator.html의 SoftCPU에서 관리
   * 이 파일은 v86과의 인터페이스 패치만 담당
   */
  global.V86CPUBridge = {

    /**
     * v86 인스턴스에 CPUID 레벨 패치 적용
     * @param {V86} emulator - v86 인스턴스
     * @param {number} cpuid_level - CPUID max level (예: 0x10, 0x20)
     * @param {Object} exec_model - 실행 모델 파라미터
     */
    apply: function (emulator, cpuid_level, exec_model) {
      if (!emulator) return;
      try {
        // v86 내부 CPU 오브젝트에 접근
        const cpu = emulator.v86?.cpu;
        if (!cpu) return;

        // CPUID 최대 레벨 패치
        if (typeof cpu.set_cpuid_level === 'function') {
          cpu.set_cpuid_level(cpuid_level || 0x10);
        }

        // 실행 모델 힌트 (v86가 지원하는 경우)
        if (exec_model) {
          if (exec_model.ipc && typeof cpu.set_ipc_hint === 'function') {
            cpu.set_ipc_hint(exec_model.ipc);
          }
        }
      } catch (e) {
        // 패치 실패는 조용히 무시 (에뮬레이션은 계속됨)
      }
    },

    /**
     * 메모리 크기 검증 및 정규화
     * @param {number} ram_mb
     * @param {Object} spec - CPU 스펙
     * @returns {number} 바이트 단위 메모리 크기
     */
    normalize_memory: function (ram_mb, spec) {
      // 32bit CPU는 최대 4GB, 실용적으로는 512MB 권장
      const is_32bit = spec?.arch === 'x86';
      const max_mb   = is_32bit ? 512 : 4096;
      const safe_mb  = Math.min(Math.max(ram_mb || 512, 128), max_mb);

      // CPU별 강제 메모리 크기 (레트로 CPU)
      if (spec?.v86_opts?.memory_size) {
        return spec.v86_opts.memory_size;
      }
      return safe_mb * 1024 * 1024;
    },

    /**
     * v86 boot_order 결정
     * @param {boolean} has_iso
     * @param {boolean} has_hdd
     * @returns {number}
     */
    boot_order: function (has_iso, has_hdd) {
      if (has_iso && has_hdd) return 0x132;  // CDROM → HDD
      if (has_iso)            return 0x123;  // CDROM → FDD → HDD
      if (has_hdd)            return 0x213;  // HDD → CDROM → FDD
      return 0x231;                           // FDD → HDD → CDROM (기본)
    },
  };

})(window);
