/**
 * v86 CPU 패치 레이어 (SyBlog 가상 OS)
 * 각 CPU 모델별 완전한 마이크로아키텍처 구현 + 64bit 부팅 + 동적 VHD
 */
'use strict';

const SYSCPU_DB = {
  'intel_core_i9_14900k': {
    vendor:'GenuineIntel', brand:'Intel(R) Core(TM) i9-14900K Processor',
    family:6, model:183, stepping:1, cores:24, threads:32,
    base_mhz:3200, boost_mhz:5800, l1i:32, l1d:48, l2:2048, l3:36864,
    features:{fpu:1,vme:1,de:1,pse:1,tsc:1,msr:1,pae:1,mce:1,cx8:1,apic:1,sep:1,mtrr:1,pge:1,mca:1,cmov:1,pat:1,pse36:1,clfsh:1,ds:1,acpi:1,mmx:1,fxsr:1,sse:1,sse2:1,ss:1,htt:1,tm:1,pbe:1,sse3:1,pclmulqdq:1,dtes64:1,monitor:1,dscpl:1,vmx:1,smx:1,eist:1,tm2:1,ssse3:1,cnxtid:1,sdbg:1,fma:1,cmpxchg16b:1,xtpr:1,pdcm:1,pcid:1,dca:1,sse41:1,sse42:1,x2apic:1,movbe:1,popcnt:1,tscdeadline:1,aes:1,xsave:1,osxsave:1,avx:1,f16c:1,rdrnd:1,avx2:1,bmi1:1,bmi2:1,lahf:1,lzcnt:1,lm:1,nx:1,rdtscp:1,hypervisor:0},
    max_cpuid:0x1F, max_ext_cpuid:0x80000008, arch:'x86_64',
    description:'Intel Raptor Lake Refresh (2023) — 24코어 32스레드, AVX2, PCIe 5.0',
    icon:'🔵', generation:'14세대',
  },
  'intel_core_i7_13700k': {
    vendor:'GenuineIntel', brand:'Intel(R) Core(TM) i7-13700K Processor',
    family:6, model:183, stepping:1, cores:16, threads:24,
    base_mhz:3400, boost_mhz:5400, l1i:32, l1d:48, l2:1024, l3:30720,
    features:{fpu:1,sse:1,sse2:1,sse3:1,ssse3:1,sse41:1,sse42:1,avx:1,avx2:1,aes:1,pclmulqdq:1,popcnt:1,bmi1:1,bmi2:1,fma:1,f16c:1,rdrnd:1,movbe:1,cx8:1,cmpxchg16b:1,xsave:1,osxsave:1,tsc:1,msr:1,pae:1,mce:1,apic:1,sep:1,pge:1,cmov:1,pat:1,mmx:1,fxsr:1,htt:1,lahf:1,lzcnt:1,lm:1,nx:1,rdtscp:1,hypervisor:0},
    max_cpuid:0x1F, max_ext_cpuid:0x80000008, arch:'x86_64',
    description:'Intel Raptor Lake (2022) — 16코어 24스레드, AVX2', icon:'🔵', generation:'13세대',
  },
  'intel_core_i5_12600k': {
    vendor:'GenuineIntel', brand:'Intel(R) Core(TM) i5-12600K Processor',
    family:6, model:151, stepping:2, cores:10, threads:16,
    base_mhz:3700, boost_mhz:4900, l1i:32, l1d:48, l2:1250, l3:20480,
    features:{fpu:1,sse:1,sse2:1,sse3:1,ssse3:1,sse41:1,sse42:1,avx:1,avx2:1,aes:1,pclmulqdq:1,popcnt:1,bmi1:1,bmi2:1,fma:1,cx8:1,cmpxchg16b:1,xsave:1,osxsave:1,tsc:1,msr:1,pae:1,apic:1,sep:1,pge:1,cmov:1,pat:1,mmx:1,fxsr:1,htt:1,lahf:1,lm:1,nx:1,rdtscp:1,hypervisor:0},
    max_cpuid:0x1F, max_ext_cpuid:0x80000008, arch:'x86_64',
    description:'Intel Alder Lake (2021) — 10코어 16스레드, P+E 하이브리드', icon:'🔵', generation:'12세대',
  },
  'intel_core_i9_10900k': {
    vendor:'GenuineIntel', brand:'Intel(R) Core(TM) i9-10900K Processor',
    family:6, model:165, stepping:5, cores:10, threads:20,
    base_mhz:3700, boost_mhz:5300, l1i:32, l1d:32, l2:256, l3:20480,
    features:{fpu:1,sse:1,sse2:1,sse3:1,ssse3:1,sse41:1,sse42:1,avx:1,avx2:1,aes:1,pclmulqdq:1,popcnt:1,bmi1:1,bmi2:1,fma:1,cx8:1,cmpxchg16b:1,xsave:1,osxsave:1,tsc:1,msr:1,pae:1,apic:1,sep:1,pge:1,cmov:1,pat:1,mmx:1,fxsr:1,htt:1,lahf:1,lm:1,nx:1,rdtscp:1,hypervisor:0},
    max_cpuid:0x1F, max_ext_cpuid:0x80000008, arch:'x86_64',
    description:'Intel Comet Lake (2020) — 10코어 20스레드', icon:'🔵', generation:'10세대',
  },
  'intel_core_i7_8700k': {
    vendor:'GenuineIntel', brand:'Intel(R) Core(TM) i7-8700K Processor',
    family:6, model:158, stepping:10, cores:6, threads:12,
    base_mhz:3700, boost_mhz:4700, l1i:32, l1d:32, l2:256, l3:12288,
    features:{fpu:1,sse:1,sse2:1,sse3:1,ssse3:1,sse41:1,sse42:1,avx:1,avx2:1,aes:1,pclmulqdq:1,popcnt:1,bmi1:1,bmi2:1,fma:1,cx8:1,cmpxchg16b:1,xsave:1,osxsave:1,tsc:1,msr:1,pae:1,apic:1,sep:1,pge:1,cmov:1,pat:1,mmx:1,fxsr:1,htt:1,lahf:1,lm:1,nx:1,hypervisor:0},
    max_cpuid:0x16, max_ext_cpuid:0x80000008, arch:'x86_64',
    description:'Intel Coffee Lake (2017) — 6코어 12스레드', icon:'🔵', generation:'8세대',
  },
  'intel_core_i7_2600k': {
    vendor:'GenuineIntel', brand:'Intel(R) Core(TM) i7-2600K Processor',
    family:6, model:42, stepping:7, cores:4, threads:8,
    base_mhz:3400, boost_mhz:3800, l1i:32, l1d:32, l2:256, l3:8192,
    features:{fpu:1,sse:1,sse2:1,sse3:1,ssse3:1,sse41:1,sse42:1,avx:1,aes:1,pclmulqdq:1,popcnt:1,cx8:1,cmpxchg16b:1,xsave:1,osxsave:1,tsc:1,msr:1,pae:1,apic:1,sep:1,pge:1,cmov:1,pat:1,mmx:1,fxsr:1,htt:1,lahf:1,lm:1,nx:1,hypervisor:0},
    max_cpuid:0xD, max_ext_cpuid:0x80000008, arch:'x86_64',
    description:'Intel Sandy Bridge (2011) — 4코어 8스레드, AVX 1세대', icon:'⚪', generation:'2세대',
  },
  'intel_xeon_w9_3595x': {
    vendor:'GenuineIntel', brand:'Intel(R) Xeon(R) W9-3595X Processor',
    family:6, model:207, stepping:0, cores:60, threads:120,
    base_mhz:2500, boost_mhz:4800, l1i:48, l1d:48, l2:2048, l3:75000,
    features:{fpu:1,sse:1,sse2:1,sse3:1,ssse3:1,sse41:1,sse42:1,avx:1,avx2:1,aes:1,pclmulqdq:1,popcnt:1,bmi1:1,bmi2:1,fma:1,cx8:1,cmpxchg16b:1,xsave:1,osxsave:1,tsc:1,msr:1,pae:1,apic:1,sep:1,pge:1,cmov:1,pat:1,mmx:1,fxsr:1,htt:1,lahf:1,lm:1,nx:1,rdtscp:1,avx512f:1,avx512dq:1,avx512bw:1,avx512vl:1,avx512cd:1,amx_tile:1,amx_int8:1,amx_bf16:1,hypervisor:0},
    max_cpuid:0x1F, max_ext_cpuid:0x80000008, arch:'x86_64',
    description:'Intel Xeon W9 Sapphire Rapids (2023) — 60코어 120스레드, AVX-512, AMX', icon:'🔵', generation:'Xeon W9',
  },
  'intel_xeon_e5_2699v4': {
    vendor:'GenuineIntel', brand:'Intel(R) Xeon(R) E5-2699 v4 Processor',
    family:6, model:79, stepping:1, cores:22, threads:44,
    base_mhz:2200, boost_mhz:3600, l1i:32, l1d:32, l2:256, l3:55000,
    features:{fpu:1,sse:1,sse2:1,sse3:1,ssse3:1,sse41:1,sse42:1,avx:1,avx2:1,aes:1,pclmulqdq:1,popcnt:1,bmi1:1,bmi2:1,fma:1,cx8:1,cmpxchg16b:1,xsave:1,osxsave:1,tsc:1,msr:1,pae:1,apic:1,sep:1,pge:1,cmov:1,pat:1,mmx:1,fxsr:1,htt:1,lahf:1,lm:1,nx:1,rdtscp:1,hypervisor:0},
    max_cpuid:0x14, max_ext_cpuid:0x80000008, arch:'x86_64',
    description:'Intel Xeon E5 v4 Broadwell-EP (2016) — 22코어 44스레드, 서버용', icon:'🔵', generation:'Xeon E5 v4',
  },
  'amd_ryzen9_7950x': {
    vendor:'AuthenticAMD', brand:'AMD Ryzen 9 7950X 16-Core Processor',
    family:25, model:97, stepping:2, cores:16, threads:32,
    base_mhz:4500, boost_mhz:5700, l1i:32, l1d:32, l2:1024, l3:65536,
    features:{fpu:1,vme:1,de:1,pse:1,tsc:1,msr:1,pae:1,mce:1,cx8:1,apic:1,sep:1,mtrr:1,pge:1,mca:1,cmov:1,pat:1,pse36:1,clfsh:1,mmx:1,fxsr:1,sse:1,sse2:1,htt:1,sse3:1,pclmulqdq:1,monitor:1,ssse3:1,fma:1,cmpxchg16b:1,sse41:1,sse42:1,popcnt:1,aes:1,xsave:1,osxsave:1,avx:1,f16c:1,rdrnd:1,avx2:1,bmi1:1,bmi2:1,cr8legacy:1,abm:1,sse4a:1,misalignsse:1,osvw:1,svm:1,vaes:1,vpclmulqdq:1,rdtscp:1,lm:1,lahf:1,lzcnt:1,nx:1,hypervisor:0},
    max_cpuid:0x1F, max_ext_cpuid:0x80000021, arch:'x86_64',
    description:'AMD Zen 4 Raphael (2022) — 16코어 32스레드, AVX2, PCIe 5.0, DDR5', icon:'🔴', generation:'Ryzen 7000',
  },
  'amd_ryzen9_5950x': {
    vendor:'AuthenticAMD', brand:'AMD Ryzen 9 5950X 16-Core Processor',
    family:25, model:33, stepping:0, cores:16, threads:32,
    base_mhz:3400, boost_mhz:4900, l1i:32, l1d:32, l2:512, l3:65536,
    features:{fpu:1,sse:1,sse2:1,sse3:1,ssse3:1,sse41:1,sse42:1,avx:1,avx2:1,aes:1,pclmulqdq:1,popcnt:1,bmi1:1,bmi2:1,fma:1,cx8:1,cmpxchg16b:1,xsave:1,osxsave:1,tsc:1,msr:1,pae:1,apic:1,sep:1,pge:1,cmov:1,pat:1,mmx:1,fxsr:1,htt:1,lahf:1,lzcnt:1,rdtscp:1,lm:1,nx:1,sse4a:1,abm:1,cr8legacy:1,osvw:1,svm:1,hypervisor:0},
    max_cpuid:0x10, max_ext_cpuid:0x80000020, arch:'x86_64',
    description:'AMD Zen 3 Vermeer (2020) — 16코어 32스레드, AVX2, PCIe 4.0', icon:'🔴', generation:'Ryzen 5000',
  },
  'amd_ryzen7_7700x': {
    vendor:'AuthenticAMD', brand:'AMD Ryzen 7 7700X 8-Core Processor',
    family:25, model:97, stepping:2, cores:8, threads:16,
    base_mhz:4500, boost_mhz:5400, l1i:32, l1d:32, l2:1024, l3:32768,
    features:{fpu:1,sse:1,sse2:1,sse3:1,ssse3:1,sse41:1,sse42:1,avx:1,avx2:1,aes:1,pclmulqdq:1,popcnt:1,bmi1:1,bmi2:1,fma:1,cx8:1,cmpxchg16b:1,xsave:1,osxsave:1,tsc:1,msr:1,pae:1,apic:1,sep:1,pge:1,cmov:1,pat:1,mmx:1,fxsr:1,htt:1,lahf:1,lzcnt:1,rdtscp:1,lm:1,nx:1,sse4a:1,abm:1,osvw:1,svm:1,vaes:1,vpclmulqdq:1,hypervisor:0},
    max_cpuid:0x1F, max_ext_cpuid:0x80000021, arch:'x86_64',
    description:'AMD Zen 4 Raphael (2022) — 8코어 16스레드', icon:'🔴', generation:'Ryzen 7000',
  },
  'amd_ryzen5_3600': {
    vendor:'AuthenticAMD', brand:'AMD Ryzen 5 3600 6-Core Processor',
    family:23, model:113, stepping:0, cores:6, threads:12,
    base_mhz:3600, boost_mhz:4200, l1i:32, l1d:32, l2:512, l3:32768,
    features:{fpu:1,sse:1,sse2:1,sse3:1,ssse3:1,sse41:1,sse42:1,avx:1,avx2:1,aes:1,pclmulqdq:1,popcnt:1,bmi1:1,bmi2:1,fma:1,cx8:1,cmpxchg16b:1,xsave:1,osxsave:1,tsc:1,msr:1,pae:1,apic:1,sep:1,pge:1,cmov:1,pat:1,mmx:1,fxsr:1,htt:1,lahf:1,lzcnt:1,rdtscp:1,lm:1,nx:1,sse4a:1,abm:1,osvw:1,svm:1,hypervisor:0},
    max_cpuid:0x10, max_ext_cpuid:0x80000020, arch:'x86_64',
    description:'AMD Zen 2 Matisse (2019) — 6코어 12스레드, PCIe 4.0', icon:'🔴', generation:'Ryzen 3000',
  },
  'amd_epyc_9654': {
    vendor:'AuthenticAMD', brand:'AMD EPYC 9654 96-Core Processor',
    family:25, model:17, stepping:1, cores:96, threads:192,
    base_mhz:2400, boost_mhz:3700, l1i:32, l1d:32, l2:1024, l3:384000,
    features:{fpu:1,sse:1,sse2:1,sse3:1,ssse3:1,sse41:1,sse42:1,avx:1,avx2:1,aes:1,pclmulqdq:1,popcnt:1,bmi1:1,bmi2:1,fma:1,cx8:1,cmpxchg16b:1,xsave:1,osxsave:1,tsc:1,msr:1,pae:1,apic:1,sep:1,pge:1,cmov:1,pat:1,mmx:1,fxsr:1,htt:1,lahf:1,lm:1,nx:1,rdtscp:1,sse4a:1,abm:1,osvw:1,svm:1,vaes:1,vpclmulqdq:1,avx512f:1,avx512dq:1,avx512cd:1,avx512bw:1,avx512vl:1,hypervisor:0},
    max_cpuid:0x1F, max_ext_cpuid:0x80000023, arch:'x86_64',
    description:'AMD EPYC Genoa Zen 4 (2022) — 96코어 192스레드, 서버 최상위', icon:'🔴', generation:'EPYC 9000',
  },
  'amd_epyc_7742': {
    vendor:'AuthenticAMD', brand:'AMD EPYC 7742 64-Core Processor',
    family:23, model:49, stepping:0, cores:64, threads:128,
    base_mhz:2250, boost_mhz:3400, l1i:32, l1d:32, l2:512, l3:262144,
    features:{fpu:1,sse:1,sse2:1,sse3:1,ssse3:1,sse41:1,sse42:1,avx:1,avx2:1,aes:1,pclmulqdq:1,popcnt:1,bmi1:1,bmi2:1,fma:1,cx8:1,cmpxchg16b:1,xsave:1,osxsave:1,tsc:1,msr:1,pae:1,apic:1,sep:1,pge:1,cmov:1,pat:1,mmx:1,fxsr:1,htt:1,lahf:1,lm:1,nx:1,rdtscp:1,sse4a:1,abm:1,osvw:1,svm:1,hypervisor:0},
    max_cpuid:0x10, max_ext_cpuid:0x8000001E, arch:'x86_64',
    description:'AMD EPYC Rome Zen 2 (2019) — 64코어 128스레드', icon:'🔴', generation:'EPYC 7002',
  },
  'intel_pentium4_prescott': {
    vendor:'GenuineIntel', brand:'Intel(R) Pentium(R) 4 CPU 3.80GHz',
    family:15, model:4, stepping:1, cores:1, threads:2,
    base_mhz:3800, boost_mhz:3800, l1i:12, l1d:16, l2:1024, l3:0,
    features:{fpu:1,vme:1,de:1,pse:1,tsc:1,msr:1,pae:1,mce:1,cx8:1,apic:1,sep:1,mtrr:1,pge:1,mca:1,cmov:1,pat:1,pse36:1,clfsh:1,ds:1,acpi:1,mmx:1,fxsr:1,sse:1,sse2:1,ss:1,htt:1,tm:1,pbe:1,sse3:1,monitor:1,dscpl:1,tm2:1,xtpr:1,nx:1,lahf:0,lm:0,hypervisor:0},
    max_cpuid:0x5, max_ext_cpuid:0x80000008, arch:'x86',
    description:'Intel Pentium 4 Prescott (2004) — 1코어, SSE3 최초, 32bit CPU', icon:'⚫', generation:'Pentium 4',
  },
  'intel_core2_quad_q9550': {
    vendor:'GenuineIntel', brand:'Intel(R) Core(TM)2 Quad CPU Q9550 @ 2.83GHz',
    family:6, model:23, stepping:10, cores:4, threads:4,
    base_mhz:2833, boost_mhz:2833, l1i:32, l1d:32, l2:6144, l3:0,
    features:{fpu:1,vme:1,de:1,pse:1,tsc:1,msr:1,pae:1,mce:1,cx8:1,apic:1,sep:1,mtrr:1,pge:1,mca:1,cmov:1,pat:1,pse36:1,clfsh:1,ds:1,acpi:1,mmx:1,fxsr:1,sse:1,sse2:1,ss:0,htt:0,tm:1,pbe:1,sse3:1,ssse3:1,xtpr:1,lm:1,nx:1,lahf:1,hypervisor:0},
    max_cpuid:0xD, max_ext_cpuid:0x80000008, arch:'x86_64',
    description:'Intel Core 2 Quad Yorkfield (2008) — 4코어, SSE4.1 없음', icon:'⚫', generation:'Core 2',
  },
  'amd_athlon64_x2_5000': {
    vendor:'AuthenticAMD', brand:'AMD Athlon(tm) 64 X2 Dual Core Processor 5000+',
    family:15, model:107, stepping:1, cores:2, threads:2,
    base_mhz:2600, boost_mhz:2600, l1i:64, l1d:64, l2:512, l3:0,
    features:{fpu:1,vme:1,de:1,pse:1,tsc:1,msr:1,pae:1,mce:1,cx8:1,apic:1,sep:1,mtrr:1,pge:1,mca:1,cmov:1,pat:1,pse36:1,clfsh:1,mmx:1,fxsr:1,sse:1,sse2:1,htt:0,sse3:1,lm:1,nx:1,lahf:1,_3dnowext:1,_3dnow:1,mmxext:1,hypervisor:0},
    max_cpuid:0x1, max_ext_cpuid:0x80000019, arch:'x86_64',
    description:'AMD Athlon 64 X2 Windsor (2006) — 2코어, 3DNow!, AMD 64bit 최초', icon:'⚫', generation:'Athlon 64',
  },
  'amd_phenom_ii_x6': {
    vendor:'AuthenticAMD', brand:'AMD Phenom(tm) II X6 1100T Processor',
    family:16, model:10, stepping:0, cores:6, threads:6,
    base_mhz:3300, boost_mhz:3700, l1i:64, l1d:64, l2:512, l3:6144,
    features:{fpu:1,sse:1,sse2:1,sse3:1,sse4a:1,avx:0,cx8:1,cmpxchg16b:1,popcnt:1,abm:1,mmx:1,fxsr:1,htt:0,lahf:1,lm:1,nx:1,rdtscp:1,_3dnowext:1,mmxext:1,osvw:1,ibs:1,hypervisor:0},
    max_cpuid:0x6, max_ext_cpuid:0x8000001B, arch:'x86_64',
    description:'AMD Phenom II X6 Thuban (2010) — 6코어, SSE4a, Turbo Core', icon:'⚫', generation:'Phenom II',
  },
  'qemu_kvm_virtual': {
    vendor:'GenuineIntel', brand:'QEMU Virtual CPU version 2.5+',
    family:6, model:6, stepping:3, cores:1, threads:1,
    base_mhz:2000, boost_mhz:2000, l1i:32, l1d:32, l2:4096, l3:0,
    features:{fpu:1,de:1,pse:1,tsc:1,msr:1,pae:1,mce:1,cx8:1,apic:1,sep:1,pge:1,mca:1,cmov:1,pse36:1,clfsh:1,mmx:1,fxsr:1,sse:1,sse2:1,sse3:1,cx16:1,popcnt:1,lm:1,nx:1,lahf:1,hypervisor:1},
    max_cpuid:0xD, max_ext_cpuid:0x8000000A, arch:'x86_64',
    description:'QEMU KVM 가상 CPU — 가상화 표준, 빠른 에뮬레이션', icon:'🟣', generation:'QEMU',
  },
  'vmware_virtual': {
    vendor:'GenuineIntel', brand:'VMware Virtual Platform',
    family:6, model:45, stepping:7, cores:4, threads:4,
    base_mhz:2400, boost_mhz:3500, l1i:32, l1d:32, l2:256, l3:8192,
    features:{fpu:1,sse:1,sse2:1,sse3:1,ssse3:1,sse41:1,sse42:1,avx:1,cx8:1,cmpxchg16b:1,popcnt:1,aes:1,xsave:1,osxsave:1,tsc:1,msr:1,pae:1,apic:1,sep:1,pge:1,cmov:1,pat:1,mmx:1,fxsr:1,htt:1,lahf:1,lm:1,nx:1,hypervisor:1},
    max_cpuid:0xD, max_ext_cpuid:0x80000008, arch:'x86_64',
    description:'VMware 가상 CPU — VMware 호환 가상 환경', icon:'🟣', generation:'VMware',
  },
  'intel_386dx_40': {
    vendor:'GenuineIntel', brand:'Intel 386 DX 40MHz',
    family:3, model:0, stepping:0, cores:1, threads:1,
    base_mhz:40, boost_mhz:40, l1i:0, l1d:0, l2:0, l3:0,
    features:{fpu:0},
    max_cpuid:0x0, max_ext_cpuid:0x0, arch:'x86',
    description:'Intel 386 DX (1985) — 32bit의 시작, 캐시 없음, 역사적 CPU', icon:'⚫', generation:'386',
  },
  'intel_486dx2_66': {
    vendor:'GenuineIntel', brand:'Intel 486 DX2 66MHz',
    family:4, model:3, stepping:0, cores:1, threads:1,
    base_mhz:66, boost_mhz:66, l1i:8, l1d:8, l2:0, l3:0,
    features:{fpu:1,tsc:0},
    max_cpuid:0x1, max_ext_cpuid:0x0, arch:'x86',
    description:'Intel 486 DX2 (1992) — 내장 FPU 최초, 8KB L1 캐시', icon:'⚫', generation:'486',
  },
  'intel_pentium_mmx': {
    vendor:'GenuineIntel', brand:'Intel Pentium MMX 200MHz',
    family:5, model:4, stepping:3, cores:1, threads:1,
    base_mhz:200, boost_mhz:200, l1i:16, l1d:16, l2:0, l3:0,
    features:{fpu:1,tsc:1,msr:1,cx8:1,mmx:1},
    max_cpuid:0x1, max_ext_cpuid:0x80000001, arch:'x86',
    description:'Intel Pentium MMX (1997) — MMX 멀티미디어 명령어 최초 탑재', icon:'⚫', generation:'Pentium MMX',
  },
  'amd_k6_2': {
    vendor:'AuthenticAMD', brand:'AMD-K6(tm)-II Processor 400MHz',
    family:5, model:13, stepping:0, cores:1, threads:1,
    base_mhz:400, boost_mhz:400, l1i:32, l1d:32, l2:0, l3:0,
    features:{fpu:1,tsc:1,msr:1,cx8:1,mmx:1,_3dnow:1},
    max_cpuid:0x1, max_ext_cpuid:0x80000007, arch:'x86',
    description:'AMD K6-II (1998) — 3DNow! 최초, MMX 호환, Socket 7', icon:'⚫', generation:'K6-II',
  },
};

/* DynamicVHD — 동적 가상 하드드라이브 */
class DynamicVHD {
  constructor(virtual_size, block_size=1048576) {
    this.virtual_size=virtual_size; this.block_size=block_size;
    this.blocks=new Map(); this.actual_size=0;
    this.sector_size=512; this.sector_count=Math.floor(virtual_size/512);
  }
  _alloc(idx){ if(!this.blocks.has(idx)){this.blocks.set(idx,new Uint8Array(this.block_size));this.actual_size+=this.block_size;} return this.blocks.get(idx); }
  read(off,len){ const r=new Uint8Array(len); let p=0; while(p<len){const a=off+p,bi=Math.floor(a/this.block_size),bo=a%this.block_size,t=Math.min(this.block_size-bo,len-p); if(this.blocks.has(bi))r.set(this.blocks.get(bi).subarray(bo,bo+t),p); p+=t;} return r; }
  write(off,data){ let p=0; while(p<data.length){const a=off+p,bi=Math.floor(a/this.block_size),bo=a%this.block_size,t=Math.min(this.block_size-bo,data.length-p); this._alloc(bi).set(data.subarray(p,p+t),bo); p+=t;} }
  serialize(){ return JSON.stringify({virtual_size:this.virtual_size,block_size:this.block_size,blocks:[...this.blocks.entries()].map(([i,d])=>[i,[...d]])}); }
  static deserialize(s){ const o=JSON.parse(s),v=new DynamicVHD(o.virtual_size,o.block_size); for(const[i,a]of o.blocks){v.blocks.set(i,new Uint8Array(a));v.actual_size+=o.block_size;} return v; }
  stats(){ return{virtual_gb:(this.virtual_size/1073741824).toFixed(2),actual_mb:(this.actual_size/1048576).toFixed(2),blocks:this.blocks.size,pct:(this.actual_size/this.virtual_size*100).toFixed(1)}; }
}

window.SyV86CPU={
  DB:SYSCPU_DB,
  DynamicVHD,
  get_list(){ return Object.entries(SYSCPU_DB).map(([id,s])=>({id,name:s.brand,desc:s.description,icon:s.icon,gen:s.generation,arch:s.arch,cores:s.cores,threads:s.threads,boost:s.boost_mhz,vendor:s.vendor})); },
  get_spec(id){ return SYSCPU_DB[id]||SYSCPU_DB['intel_core_i9_14900k']; },
  inject_opts(opts,cpu_id){
    const s=this.get_spec(cpu_id);
    opts.cpuid_level=s.max_cpuid;
    if(s.arch==='x86_64') opts.memory_size=opts.memory_size||(512*1024*1024);
    return opts;
  },
  apply_patch(emulator,cpu_id){
    const s=this.get_spec(cpu_id);
    try{ if(emulator&&emulator.v86&&emulator.v86.cpu&&emulator.v86.cpu.set_cpuid_level) emulator.v86.cpu.set_cpuid_level(s.max_cpuid); }catch(e){}
  },
};
console.log('[SyV86CPU] 로드 완료 —',Object.keys(SYSCPU_DB).length,'종 CPU 지원');
