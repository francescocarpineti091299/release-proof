//
// Minimal nRF52840 NVMC (non-volatile memory controller) model for Renode.
// Copyright (c) 2026 ReleaseProof contributors. SPDX-License-Identifier: MIT
//
// Upstream Renode (1.16.1) has no NVMC model, so the Zephyr nRF flash driver used by MCUboot
// cannot erase pages. This model implements just what MCUboot needs:
//   READY / READYNEXT always 1 (operations complete instantly in virtual time),
//   CONFIG (WEN) stored, ERASEPAGE / ERASEPCR0 / ERASEPCR1 / ERASEPAGEPARTIAL erase one page to 0xFF,
//   ERASEALL erases the whole code flash. Word writes go straight to the flash MappedMemory.
// It does not model write-enable enforcement, 1->0-only programming, timing or UICR erase.
//
using Antmicro.Renode.Core;
using Antmicro.Renode.Core.Structure.Registers;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.Memory;

namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    public class RP_NRF52840_NVMC : BasicDoubleWordPeripheral, IKnownSize
    {
        public RP_NRF52840_NVMC(IMachine machine, MappedMemory flash, long pageSize = 0x1000) : base(machine)
        {
            this.flash = flash;
            this.pageSize = pageSize;
            erasedPage = new byte[pageSize];
            for(var i = 0; i < erasedPage.Length; i++)
            {
                erasedPage[i] = 0xFF;
            }
            DefineRegisters();
        }

        public long Size => 0x1000;

        public ulong PageErases { get; private set; }

        private void ErasePage(ulong address)
        {
            var offset = (long)address & ~(pageSize - 1);
            if(offset < 0 || offset + pageSize > flash.Size)
            {
                this.Log(LogLevel.Warning, "erase request outside code flash: 0x{0:X}", address);
                return;
            }
            flash.WriteBytes(offset, erasedPage, 0, (int)pageSize);
            PageErases++;
            this.Log(LogLevel.Debug, "erased page 0x{0:X}", offset);
        }

        private void EraseAll()
        {
            for(long offset = 0; offset + pageSize <= flash.Size; offset += pageSize)
            {
                flash.WriteBytes(offset, erasedPage, 0, (int)pageSize);
            }
            this.Log(LogLevel.Info, "erased all code flash");
        }

        private void DefineRegisters()
        {
            Registers.Ready.Define(this, 0x1)
                .WithFlag(0, FieldMode.Read, valueProviderCallback: _ => true, name: "READY")
                .WithReservedBits(1, 31);
            Registers.ReadyNext.Define(this, 0x1)
                .WithFlag(0, FieldMode.Read, valueProviderCallback: _ => true, name: "READYNEXT")
                .WithReservedBits(1, 31);
            Registers.Config.Define(this)
                .WithValueField(0, 2, name: "WEN")
                .WithReservedBits(2, 30);
            Registers.ErasePage.Define(this)
                .WithValueField(0, 32, FieldMode.Write, writeCallback: (_, v) => ErasePage(v), name: "ERASEPAGE");
            Registers.EraseAll.Define(this)
                .WithFlag(0, FieldMode.Write, writeCallback: (_, v) => { if(v) { EraseAll(); } }, name: "ERASEALL")
                .WithReservedBits(1, 31);
            Registers.ErasePcr0.Define(this)
                .WithValueField(0, 32, FieldMode.Write, writeCallback: (_, v) => ErasePage(v), name: "ERASEPCR0");
            Registers.EraseUicr.Define(this)
                .WithFlag(0, FieldMode.Write, name: "ERASEUICR")
                .WithReservedBits(1, 31);
            Registers.ErasePagePartial.Define(this)
                .WithValueField(0, 32, FieldMode.Write, writeCallback: (_, v) => ErasePage(v), name: "ERASEPAGEPARTIAL");
            Registers.ErasePagePartialCfg.Define(this, 0xA)
                .WithValueField(0, 7, name: "DURATION")
                .WithReservedBits(7, 25);
            Registers.ICacheCnf.Define(this)
                .WithValueField(0, 32, name: "ICACHECNF");
            Registers.IHit.Define(this)
                .WithValueField(0, 32, name: "IHIT");
            Registers.IMiss.Define(this)
                .WithValueField(0, 32, name: "IMISS");
        }

        private readonly MappedMemory flash;
        private readonly long pageSize;
        private readonly byte[] erasedPage;

        private enum Registers : long
        {
            Ready = 0x400,
            ReadyNext = 0x408,
            Config = 0x504,
            ErasePage = 0x508,
            EraseAll = 0x50C,
            ErasePcr0 = 0x510,
            EraseUicr = 0x514,
            ErasePagePartial = 0x518,
            ErasePagePartialCfg = 0x51C,
            ICacheCnf = 0x540,
            IHit = 0x548,
            IMiss = 0x54C,
        }
    }
}
