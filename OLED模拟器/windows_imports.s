/* Minimal x64 PE import table for the native launcher. */
.section .idata$2,"dr"
.globl __IMPORT_DESCRIPTOR_KERNEL32
__IMPORT_DESCRIPTOR_KERNEL32:
  .rva k32_int
  .long 0
  .long 0
  .rva k32_name
  .rva k32_iat
.globl __IMPORT_DESCRIPTOR_USER32
__IMPORT_DESCRIPTOR_USER32:
  .rva u32_int
  .long 0
  .long 0
  .rva u32_name
  .rva u32_iat

.section .idata$3,"dr"
.globl __NULL_IMPORT_DESCRIPTOR
__NULL_IMPORT_DESCRIPTOR:
  .long 0,0,0,0,0

.section .idata$4,"dr"
k32_int:
  .rva hint_GetModuleFileNameW; .long 0
  .rva hint_GetFileAttributesW; .long 0
  .rva hint_GetEnvironmentVariableW; .long 0
  .rva hint_SearchPathW; .long 0
  .rva hint_CreateProcessW; .long 0
  .rva hint_CloseHandle; .long 0
  .rva hint_ExitProcess; .long 0
  .rva hint_WaitForSingleObject; .long 0
  .rva hint_GetExitCodeProcess; .long 0
  .quad 0
u32_int:
  .rva hint_MessageBoxW; .long 0
  .quad 0

.section .idata$5,"drw"
k32_iat:
.globl __imp_GetModuleFileNameW
__imp_GetModuleFileNameW: .rva hint_GetModuleFileNameW; .long 0
.globl __imp_GetFileAttributesW
__imp_GetFileAttributesW: .rva hint_GetFileAttributesW; .long 0
.globl __imp_GetEnvironmentVariableW
__imp_GetEnvironmentVariableW: .rva hint_GetEnvironmentVariableW; .long 0
.globl __imp_SearchPathW
__imp_SearchPathW: .rva hint_SearchPathW; .long 0
.globl __imp_CreateProcessW
__imp_CreateProcessW: .rva hint_CreateProcessW; .long 0
.globl __imp_CloseHandle
__imp_CloseHandle: .rva hint_CloseHandle; .long 0
.globl __imp_ExitProcess
__imp_ExitProcess: .rva hint_ExitProcess; .long 0
.globl __imp_WaitForSingleObject
__imp_WaitForSingleObject: .rva hint_WaitForSingleObject; .long 0
.globl __imp_GetExitCodeProcess
__imp_GetExitCodeProcess: .rva hint_GetExitCodeProcess; .long 0
  .quad 0
u32_iat:
.globl __imp_MessageBoxW
__imp_MessageBoxW: .rva hint_MessageBoxW; .long 0
  .quad 0

.section .idata$6,"dr"
k32_name: .asciz "KERNEL32.dll"
  .balign 2
u32_name: .asciz "USER32.dll"
  .balign 2
hint_GetModuleFileNameW: .short 0; .asciz "GetModuleFileNameW"; .balign 2
hint_GetFileAttributesW: .short 0; .asciz "GetFileAttributesW"; .balign 2
hint_GetEnvironmentVariableW: .short 0; .asciz "GetEnvironmentVariableW"; .balign 2
hint_SearchPathW: .short 0; .asciz "SearchPathW"; .balign 2
hint_CreateProcessW: .short 0; .asciz "CreateProcessW"; .balign 2
hint_CloseHandle: .short 0; .asciz "CloseHandle"; .balign 2
hint_ExitProcess: .short 0; .asciz "ExitProcess"; .balign 2
hint_WaitForSingleObject: .short 0; .asciz "WaitForSingleObject"; .balign 2
hint_GetExitCodeProcess: .short 0; .asciz "GetExitCodeProcess"; .balign 2
hint_MessageBoxW: .short 0; .asciz "MessageBoxW"; .balign 2
