;RUN: %opt < %s %loadEnzyme -enzyme -mem2reg -instsimplify -simplifycfg -S | FileCheck %s

;#include <cblas.h>
;
;extern double __enzyme_autodiff(void *, double *, double *, double *,
;                                 double *);
;
;double g(double *restrict m, double *restrict n) {
;  double x = cblas_ddot(3, m, 1, n, 1);
;  m[0] = 11.0;
;  m[1] = 12.0;
;  m[2] = 13.0;
;  double y = x * x;
;  return y;
;}
;
;int main() {
;  double m[3] = {1, 2, 3};
;  double m1[3] = {0, 0, 0};
;  double n[3] = {4, 5, 6};
;  double n1[3] = {0, 0, 0};
;  double val = __enzyme_autodiff((void*)g, m, m1, n, n1);
;}

target datalayout = "e-m:e-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"

@__const.main.m = private unnamed_addr constant [3 x double] [double 1.000000e+00, double 2.000000e+00, double 3.000000e+00], align 16
@__const.main.n = private unnamed_addr constant [3 x double] [double 4.000000e+00, double 5.000000e+00, double 6.000000e+00], align 16

define dso_local double @g(double* noalias %m, double* noalias %n) {
entry:
  %m.addr = alloca double*, align 8
  %n.addr = alloca double*, align 8
  %x = alloca double, align 8
  %y = alloca double, align 8
  store double* %m, double** %m.addr, align 8
  store double* %n, double** %n.addr, align 8
  %0 = load double*, double** %m.addr, align 8
  %1 = load double*, double** %n.addr, align 8
  %call = call double @cblas_ddot(i32 3, double* %0, i32 1, double* %1, i32 1)
  store double %call, double* %x, align 8
  %2 = load double*, double** %m.addr, align 8
  %arrayidx = getelementptr inbounds double, double* %2, i64 0
  store double 1.100000e+01, double* %arrayidx, align 8
  %3 = load double*, double** %m.addr, align 8
  %arrayidx1 = getelementptr inbounds double, double* %3, i64 1
  store double 1.200000e+01, double* %arrayidx1, align 8
  %4 = load double*, double** %m.addr, align 8
  %arrayidx2 = getelementptr inbounds double, double* %4, i64 2
  store double 1.300000e+01, double* %arrayidx2, align 8
  %5 = load double, double* %x, align 8
  %6 = load double, double* %x, align 8
  %mul = fmul double %5, %6
  store double %mul, double* %y, align 8
  %7 = load double, double* %y, align 8
  ret double %7
}

declare dso_local double @cblas_ddot(i32, double*, i32, double*, i32)

define dso_local i32 @main() {
entry:
  %m = alloca [3 x double], align 16
  %m1 = alloca [3 x double], align 16
  %n = alloca [3 x double], align 16
  %n1 = alloca [3 x double], align 16
  %val = alloca double, align 8
  %0 = bitcast [3 x double]* %m to i8*
  call void @llvm.memcpy.p0i8.p0i8.i64(i8* align 16 %0, i8* align 16 bitcast ([3 x double]* @__const.main.m to i8*), i64 24, i1 false)
  %1 = bitcast [3 x double]* %m1 to i8*
  call void @llvm.memset.p0i8.i64(i8* align 16 %1, i8 0, i64 24, i1 false)
  %2 = bitcast [3 x double]* %n to i8*
  call void @llvm.memcpy.p0i8.p0i8.i64(i8* align 16 %2, i8* align 16 bitcast ([3 x double]* @__const.main.n to i8*), i64 24, i1 false)
  %3 = bitcast [3 x double]* %n1 to i8*
  call void @llvm.memset.p0i8.i64(i8* align 16 %3, i8 0, i64 24, i1 false)
  %arraydecay = getelementptr inbounds [3 x double], [3 x double]* %m, i32 0, i32 0
  %arraydecay1 = getelementptr inbounds [3 x double], [3 x double]* %m1, i32 0, i32 0
  %arraydecay2 = getelementptr inbounds [3 x double], [3 x double]* %n, i32 0, i32 0
  %arraydecay3 = getelementptr inbounds [3 x double], [3 x double]* %n1, i32 0, i32 0
  %call = call double @__enzyme_autodiff(i8* bitcast (double (double*, double*)* @g to i8*), double* %arraydecay, double* %arraydecay1, double* %arraydecay2, double* %arraydecay3)
  store double %call, double* %val, align 8
  ret i32 0
}

declare void @llvm.memcpy.p0i8.p0i8.i64(i8* nocapture writeonly, i8* nocapture readonly, i64, i1)

declare void @llvm.memset.p0i8.i64(i8* nocapture writeonly, i8, i64, i1)

declare dso_local double @__enzyme_autodiff(i8*, double*, double*, double*, double*)

;CHECK:define internal void @diffeg(double* noalias %m, double* %"m'", double* noalias %n, double* %"n'", double %differeturn) {
;CHECK-NEXT:entry:
;CHECK-NEXT:  %malloccall = tail call i8* @malloc(i64 mul (i64 ptrtoint (double* getelementptr (double, double* null, i32 1) to i64), i64 3))
;CHECK-NEXT:  %0 = bitcast i8* %malloccall to double*
;CHECK-NEXT:  call void @__enzyme_memcpy_doubleda0sa0stride(double* %0, double* %m, i32 3, i32 1)
;CHECK-NEXT:  %call = call double @cblas_ddot(i32 3, double* nocapture readonly %m, i32 1, double* nocapture readonly %n, i32 1)
;CHECK-NEXT:  store double 1.100000e+01, double* %m, align 8
;CHECK-NEXT:  %"arrayidx1'ipg" = getelementptr inbounds double, double* %"m'", i64 1
;CHECK-NEXT:  %arrayidx1 = getelementptr inbounds double, double* %m, i64 1
;CHECK-NEXT:  store double 1.200000e+01, double* %arrayidx1, align 8
;CHECK-NEXT:  %"arrayidx2'ipg" = getelementptr inbounds double, double* %"m'", i64 2
;CHECK-NEXT:  %arrayidx2 = getelementptr inbounds double, double* %m, i64 2
;CHECK-NEXT:  store double 1.300000e+01, double* %arrayidx2, align 8
;CHECK-NEXT:  %m0diffecall = fmul fast double %differeturn, %call
;CHECK-NEXT:  %m1diffecall = fmul fast double %differeturn, %call
;CHECK-NEXT:  %1 = fadd fast double %m0diffecall, %m1diffecall
;CHECK-NEXT:  store double 0.000000e+00, double* %"arrayidx2'ipg", align 8
;CHECK-NEXT:  store double 0.000000e+00, double* %"arrayidx1'ipg", align 8
;CHECK-NEXT:  store double 0.000000e+00, double* %"m'", align 8
;CHECK-NEXT:  call void @cblas_daxpy(i32 3, double %1, double* %0, i32 1, double* %"n'", i32 1)
;CHECK-NEXT:  tail call void @free(i8* %malloccall)
;CHECK-NEXT:  call void @cblas_daxpy(i32 3, double %1, double* %n, i32 1, double* %"m'", i32 1)
;CHECK-NEXT:  ret void
;CHECK-NEXT:}

;CHECK:declare void @cblas_daxpy(i32, double, double*, i32, double*, i32)
