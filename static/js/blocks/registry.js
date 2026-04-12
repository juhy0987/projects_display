// ── Block Registry ────────────────────────────────────────────────────────────
//
// 블록 모듈 등록/조회 싱글턴.
// 각 블록 모듈은 { type, create } 계약을 구현하고 registry.register()로 등록한다.
//
// 블록 모듈 계약(interface):
//   type   {string}                            - 블록 타입 식별자 (예: 'text')
//   create (block, opts) => HTMLElement        - 블록 DOM 요소 생성
//     block   {object}  - 서버에서 받은 블록 데이터
//     opts    {object}
//       callbacks    {BlockCallbacks}           - 글로벌 콜백 객체
//       renderBlock  (block, parentBlockId?) => HTMLElement
//                                               - 자식 블록 재귀 렌더링용

export class BlockRegistry {
  constructor() {
    /** @type {Map<string, { type: string, create: Function }>} */
    this._modules = new Map();
  }

  /**
   * 블록 모듈을 등록한다.
   * @param {{ type: string, create: Function }} module
   */
  register(module) {
    if (!module.type || typeof module.create !== "function") {
      throw new Error(`블록 모듈은 type 과 create 를 내보내야 합니다: ${JSON.stringify(module)}`);
    }
    this._modules.set(module.type, module);
  }

  /**
   * 블록 데이터로 DOM 요소를 생성한다.
   * @param {object} block
   * @param {object} opts - { callbacks, renderBlock }
   * @returns {HTMLElement}
   */
  create(block, opts = {}) {
    const module = this._modules.get(block.type);
    if (!module) {
      const unsupported = document.createElement("p");
      unsupported.className = "notion-block unsupported-block";
      unsupported.textContent = `지원하지 않는 블록 타입: ${block.type}`;
      return unsupported;
    }
    return module.create(block, opts);
  }

  /** 등록된 타입 목록 반환 */
  types() {
    return Array.from(this._modules.keys());
  }
}

/** 앱 전역 싱글턴 레지스트리 */
export const blockRegistry = new BlockRegistry();
